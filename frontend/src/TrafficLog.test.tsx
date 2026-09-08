import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TrafficLog from './TrafficLog.tsx'
import { decodedText, filterTraffic, hexDump, mergeTraffic, type TrafficEvent, type TrafficSnapshot } from './traffic.ts'

class FakeSource {
  static instances: FakeSource[] = []
  handler: ((event: MessageEvent<string>) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) { FakeSource.instances.push(this) }
  addEventListener(_name: string, handler: (event: MessageEvent<string>) => void) { this.handler = handler }
  emit(value: TrafficSnapshot) { act(() => this.handler?.(new MessageEvent('traffic', { data: JSON.stringify(value) }))) }
}
const event: TrafficEvent = {
  sequence: 1, timestamp: '2026-09-09T00:00:00Z', direction: 'TX', source: 10, destination: 11,
  channel_name: 'solora-link', channel_index: 3, portnum: 256, transport: 'meshtastic',
  status: 'Sent', packet_id: 12, payload_size: 3, raw_hex: '154142', message_type: 'THREAD',
  message_id: 'aaaa', correlation_id: 'bbbb', protocol_version: 1, decode_state: 'decoded',
  decoded: { title: 'Nyheter' }, parsed_fields: { title: 'Nyheter' }, decode_error: null, redacted: false,
}
function snapshot(events: TrafficEvent[] = [event], revision = 1): TrafficSnapshot {
  return { session: 'one', revision, oldest: events[0]?.sequence ?? revision + 1,
    capacity: 1000, events, registry: [{ value: 5, name: 'THREAD', sensitive: false }, { value: 3, name: 'WANT', sensitive: false }] }
}
beforeEach(() => { FakeSource.instances = []; vi.stubGlobal('EventSource', FakeSource); vi.stubGlobal('fetch', vi.fn()); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('Traffic Log', () => {
  it('opens one passive stream, renders data and parses exact HEX with offsets', () => {
    const { unmount } = render(<TrafficLog offline={false} channel="solora-link" />)
    expect(FakeSource.instances[0].url).toBe('/api/traffic/stream')
    FakeSource.instances[0].emit(snapshot())
    fireEvent.click(screen.getByRole('button', { name: 'Öppna paket 1' }))
    expect(screen.getByLabelText('Avkodad')).toHaveTextContent('Nyheter')
    fireEvent.click(screen.getByRole('button', { name: 'HEX' }))
    expect(screen.getByLabelText('Raw HEX')).toHaveTextContent('0000 15 41 42')
    fireEvent.click(screen.getByRole('button', { name: 'Parsing' }))
    expect(screen.getByLabelText('Parsing')).toHaveTextContent('protocol_version')
    expect(fetch).not.toHaveBeenCalled()
    unmount(); expect(FakeSource.instances[0].close).toHaveBeenCalledOnce()
  })

  it('pauses only presentation and resumes buffered frames', () => {
    render(<TrafficLog offline={false} channel="solora-link" />)
    const source = FakeSource.instances[0]; source.emit(snapshot())
    fireEvent.click(screen.getByRole('button', { name: 'Pausa' }))
    source.emit(snapshot([{ ...event, sequence: 2, direction: 'RX' }], 2))
    expect(screen.queryByRole('button', { name: 'Öppna paket 2' })).not.toBeInTheDocument()
    expect(source.close).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Fortsätt' }))
    expect(screen.getByRole('button', { name: 'Öppna paket 2' })).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('filters direction, registry type and node/text search locally', () => {
    render(<TrafficLog offline={false} channel="solora-link" />)
    FakeSource.instances[0].emit(snapshot([event, { ...event, sequence: 2, direction: 'RX', message_type: 'WANT' }], 2))
    fireEvent.click(within(screen.getByRole('group', { name: 'Riktning' })).getByRole('button', { name: 'RX' }))
    expect(screen.queryByRole('button', { name: 'Öppna paket 1' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Meddelandetyp'), { target: { value: 'THREAD' } })
    expect(screen.queryByRole('button', { name: 'Öppna paket 2' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Alla' }))
    fireEvent.change(screen.getByLabelText('Sök i loggen'), { target: { value: '!0000000a' } })
    expect(screen.getByRole('button', { name: 'Öppna paket 1' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Sök i loggen'), { target: { value: 'missing' } })
    expect(screen.getByText(/Inga matchande paket/)).toBeInTheDocument()
    expect(filterTraffic([event], '', '', 'nyheter')).toHaveLength(1)
    expect(filterTraffic([event], '', '', 'bbbb')).toHaveLength(1)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('retains offline rows and reconnects without alternative backend status', () => {
    const { rerender } = render(<TrafficLog offline={false} channel="solora-link" />)
    FakeSource.instances[0].emit(snapshot())
    act(() => FakeSource.instances[0].onerror?.())
    expect(screen.getByText(/återansluter automatiskt/)).toBeInTheDocument()
    rerender(<TrafficLog offline channel="solora-link" />)
    expect(FakeSource.instances[0].close).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Öppna paket 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rensa' })).toBeDisabled()
    rerender(<TrafficLog offline={false} channel="solora-link" />)
    expect(FakeSource.instances).toHaveLength(2)
    FakeSource.instances[1].emit({ ...snapshot([{ ...event, sequence: 3 }], 3), session: 'restart' })
    expect(screen.queryByRole('button', { name: 'Öppna paket 1' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Öppna paket 3' })).toBeInTheDocument()
  })

  it('clears only the diagnostic endpoint after confirmation', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(snapshot([], 2))))
    render(<TrafficLog offline={false} channel="solora-link" />)
    FakeSource.instances[0].emit(snapshot())
    fireEvent.click(screen.getByRole('button', { name: 'Rensa' }))
    expect(await screen.findByText('Diagnostikbufferten är rensad.')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/traffic', { method: 'DELETE' })
    FakeSource.instances[0].emit(snapshot()) // queued stale SSE cannot resurrect cleared data
    expect(screen.queryByRole('button', { name: 'Öppna paket 1' })).not.toBeInTheDocument()
  })

  it('exports JSON locally and copies HEX without protocol calls', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ format: 'SOLoRa Traffic Log', events: [event] })))
    const create = vi.fn(() => 'blob:test'); const revoke = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const copy = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: copy }, configurable: true })
    render(<TrafficLog offline={false} channel="solora-link" />)
    FakeSource.instances[0].emit(snapshot())
    fireEvent.click(screen.getByRole('button', { name: 'Exportera' }))
    expect(await screen.findByText(/JSON-exporten innehåller/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/traffic/export', { cache: 'no-store' })
    expect(create).toHaveBeenCalledWith(expect.any(Blob))
    fireEvent.click(screen.getByRole('button', { name: 'Öppna paket 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'HEX' }))
    fireEvent.click(screen.getByRole('button', { name: 'Kopiera HEX' }))
    expect(await screen.findByText('HEX kopierad.')).toBeInTheDocument()
    expect(copy).toHaveBeenCalledWith(hexDump('154142'))
  })

  it('keeps sensitive content hidden in every details view and uses mobile data labels', () => {
    render(<TrafficLog offline={false} channel="solora-link" />)
    FakeSource.instances[0].emit(snapshot([{ ...event, redacted: true, raw_hex: null, decoded: 'Payload hidden: sensitive message type', parsed_fields: {} }]))
    fireEvent.click(screen.getByRole('button', { name: 'Öppna paket 1' }))
    expect(screen.getByLabelText('Avkodad')).toHaveTextContent('Payload hidden')
    fireEvent.click(screen.getByRole('button', { name: 'HEX' }))
    expect(screen.getByRole('button', { name: 'Kopiera HEX' })).toBeDisabled()
    expect(screen.getByLabelText('Raw HEX')).toHaveTextContent('Payload hidden')
    expect(screen.getByText('3 B').closest('td')).toHaveAttribute('data-label', 'Storlek')
  })

  it('deduplicates stream overlap, evicts, resets and renders stable byte offsets', () => {
    expect(mergeTraffic(snapshot(), snapshot()).events).toHaveLength(1)
    expect(mergeTraffic(snapshot(), snapshot([], 2)).events).toHaveLength(0)
    expect(hexDump('41'.repeat(17))).toContain('0010  41')
  })

  it('does not reuse selected details or clear fences across server sessions', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(snapshot([], 50))))
    render(<TrafficLog offline={false} channel="solora-link" />)
    const source = FakeSource.instances[0]
    source.emit(snapshot())
    fireEvent.click(screen.getByRole('button', { name: 'Rensa' }))
    await screen.findByText('Diagnostikbufferten är rensad.')
    source.emit({ ...snapshot(), session: 'new' })
    fireEvent.click(screen.getByRole('button', { name: 'Öppna paket 1' }))
    source.emit({ ...snapshot([{ ...event, sequence: 2 }], 2), session: 'new' })
    expect(screen.getByRole('button', { name: 'Öppna paket 2' })).toBeInTheDocument()
    source.emit({ ...snapshot(), session: 'another' })
    expect(screen.queryByLabelText('Avkodad')).not.toBeInTheDocument()
  })

  it('renders human text and typed control references rather than raw JSON', () => {
    expect(decodedText(event)).toBe('Titel\nNyheter')
    expect(decodedText({ ...event, message_type: 'SYNC_POST', parsed_fields: { thread_id: 'abc', body: 'Hej' } })).toContain('Text\nHej')
    expect(decodedText({ ...event, message_type: 'WANT', parsed_fields: { objects: [{ kind: 'THREAD', id: 'abc' }] } })).toContain('Begärda objekt\nTHREAD abc')
    expect(decodedText({ ...event, message_type: 'SYNC', parsed_fields: { objects: [], reply_requested: true } })).toContain('Svar begärt: Ja')
    expect(decodedText({ ...event, message_type: 'COMMIT_ACK' })).toContain('inte Meshtastic routing ACK')
  })
})
