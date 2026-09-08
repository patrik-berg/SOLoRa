import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import App from './App.tsx'
import ApplicationStatusBar from './ApplicationStatusBar.tsx'
import { heartbeatAge, STATUS_INTERVAL, STATUS_TIMEOUT, useApplicationStatus, type StatusSummary } from './applicationStatus.ts'

const online: StatusSummary = {
  application: { state: 'online', version: 'test-beta' },
  system: { name: 'SOL1', role: 'PRIMARY' },
  meshtastic: { connection_state: 'online', connection_type: 'usb', node_id: 123 },
  primary: { node_id: null, system_name: null, last_heartbeat_at: null },
}

function Harness() { return <ApplicationStatusBar status={useApplicationStatus()} /> }
async function advance(milliseconds = 0) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds) })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-08T12:00:00Z'))
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.open = true })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.open = false })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('debounces offline, opens once per outage, marks node unknown and recovers without reload', async () => {
  const fetchMock = vi.fn().mockResolvedValue(Response.json(online))
  vi.stubGlobal('fetch', fetchMock)
  render(<Harness />)
  await advance()
  expect(screen.getByText('Application Online')).toBeInTheDocument()
  expect(screen.getByText('Node Online via USB')).toBeInTheDocument()
  expect(screen.getByText('Primary · Unknown')).toBeInTheDocument()

  fetchMock.mockRejectedValue(new Error('connection refused'))
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('Application Online')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('Application Offline')).toBeInTheDocument()
  expect(screen.getByText('Node Unknown')).toBeInTheDocument()
  expect(screen.getByRole('dialog', { name: 'SOLoRa är offline' })).toBeInTheDocument()
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Fortsätt visa sidan' }))
  await advance(STATUS_INTERVAL * 2)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledTimes(1)

  fetchMock.mockImplementation(async () => Response.json(online))
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('Application Online')).toBeInTheDocument()
  expect(screen.getByText('SOLoRa är online igen.')).toBeInTheDocument()
  expect(screen.getByText('Node Online via USB')).toBeInTheDocument()
  fetchMock.mockRejectedValue(new Error('stopped again'))
  await advance(STATUS_INTERVAL * 2)
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledTimes(2)
  fetchMock.mockImplementation(async () => Response.json(online))
  await advance(STATUS_INTERVAL)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('reachable readiness failure is degraded, not offline, and no heartbeat is fabricated', async () => {
  const fetchMock = vi.fn().mockResolvedValue(Response.json({ ...online, application: { state: 'degraded', version: 'test' } }))
  vi.stubGlobal('fetch', fetchMock)
  render(<Harness />)
  await advance()
  expect(screen.getByText('Application Degraded')).toBeInTheDocument()
  expect(screen.getByText('Node Online via USB')).toBeInTheDocument()
  expect(screen.getByText('Primary · Unknown')).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fetchMock.mockResolvedValue(new Response('failure', { status: 503 }))
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('Application Degraded')).toBeInTheDocument()
  expect(screen.getByText('Node Unknown')).toBeInTheDocument()
  fetchMock.mockResolvedValue(Response.json({ unexpected: true }))
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('Application Degraded')).toBeInTheDocument()
})

test('request timeout is bounded, non-overlapping, debounced and cancelled on unmount', async () => {
  const fetchMock = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init.signal?.addEventListener('abort', () => reject(new DOMException('timed out', 'AbortError')))
  }))
  vi.stubGlobal('fetch', fetchMock)
  const view = render(<Harness />)
  await advance(STATUS_TIMEOUT - 1)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(screen.getByText('Application Checking')).toBeInTheDocument()
  await advance(1 + STATUS_INTERVAL + STATUS_TIMEOUT)
  expect(screen.getByText('Application Offline')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  await advance(STATUS_INTERVAL)
  view.unmount()
  await advance(STATUS_INTERVAL * 3)
  expect(fetchMock).toHaveBeenCalledTimes(3)
  expect(fetchMock.mock.calls[2][1].signal?.aborted).toBe(true)
})

test('recovery through degraded closes the offline dialog and announces eventual readiness', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('offline'))
  vi.stubGlobal('fetch', fetchMock)
  render(<Harness />)
  await advance(STATUS_INTERVAL)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fetchMock.mockImplementation(async () => Response.json({ ...online, application: { state: 'degraded', version: 'test' } }))
  await advance(STATUS_INTERVAL)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByText('Application Degraded')).toBeInTheDocument()
  fetchMock.mockImplementation(async () => Response.json(online))
  await advance(STATUS_INTERVAL)
  expect(screen.getByText('SOLoRa är online igen.')).toBeInTheDocument()
})

test.each([
  ['network', 'online', 'Node Online via Network'],
  ['serial', 'online', 'Node Online via Serial'],
  [null, 'offline', 'Node Offline'],
  [null, 'unknown', 'Node Unknown'],
])('shows cached node %s/%s independently of application readiness', async (connectionType, connectionState, label) => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ...online,
    meshtastic: { ...online.meshtastic, connection_type: connectionType, connection_state: connectionState },
  })))
  render(<Harness />)
  await advance()
  expect(screen.getByText(label as string)).toBeInTheDocument()
  expect(screen.getByText('Application Online')).toBeInTheDocument()
})

test('relative heartbeat age changes locally without fetching and hides stale authority offline', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const status = { state: 'online' as const, lastOnline: Date.now(), recoveredAt: null, outage: 0,
    summary: { ...online, primary: { node_id: 1, system_name: 'Base North', last_heartbeat_at: '2026-09-08T11:59:18Z' } } }
  const view = render(<ApplicationStatusBar status={status} />)
  expect(screen.getByText('Primary · last heartbeat 00:42 ago')).toBeInTheDocument()
  await advance(1000)
  expect(screen.getByText('Primary · last heartbeat 00:43 ago')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
  view.rerender(<ApplicationStatusBar status={{ ...status, state: 'offline', outage: 1 }} />)
  expect(screen.getByText('Primary · Unknown')).toBeInTheDocument()
  expect(heartbeatAge('invalid', Date.now())).toBeNull()
  expect(heartbeatAge('2026-09-09T00:00:00Z', Date.now())).toBe('00:00')
})

test('global offline replaces misleading settings error and recovery retains unsent text', async () => {
  let stopped = false
  const fetchMock = vi.fn(async (url: string) => {
    if (stopped) throw new Error('server stopped')
    if (url === '/api/status') return Response.json(online)
    if (url === '/api/threads') return Response.json([])
    if (url === '/api/settings/system') return Response.json({ system_name: 'Base North', system_role: 'CLIENT' })
    return Response.json({ connected: false, channels: [], devices: [] })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  await advance()
  fireEvent.change(screen.getByLabelText('Ny tråd'), { target: { value: 'Unsent draft' } })
  stopped = true
  await advance(STATUS_INTERVAL * 2)
  fireEvent.click(screen.getByRole('button', { name: 'Fortsätt visa sidan' }))
  fireEvent.click(screen.getByRole('button', { name: 'Meshtastic-inställningar' }))
  await advance()
  expect(screen.queryByText('Det gick inte att läsa radioinställningarna.')).not.toBeInTheDocument()
  expect(screen.getByText('Application Offline')).toBeInTheDocument()
  expect(screen.getByText('Node Unknown')).toBeInTheDocument()
  stopped = false
  await advance(STATUS_INTERVAL)
  fireEvent.click(screen.getByRole('button', { name: 'Till forumet' }))
  expect(screen.getByLabelText('Ny tråd')).toHaveValue('Unsent draft')
  expect(screen.getByText('Application Online')).toBeInTheDocument()
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/settings/meshtastic').length).toBeGreaterThan(2)
})

test('radio-specific errors are still shown when application readiness is online', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/status') return Response.json(online)
    if (url === '/api/threads') return Response.json([])
    if (url === '/api/settings/meshtastic') throw new Error('radio settings unavailable')
    return Response.json({ system_name: 'Base North', system_role: 'CLIENT' })
  }))
  render(<App />)
  await advance()
  fireEvent.click(screen.getByRole('button', { name: 'Meshtastic-inställningar' }))
  await advance()
  expect(screen.getByText('Application Online')).toBeInTheDocument()
  expect(screen.getByText('Det gick inte att läsa radioinställningarna.')).toBeInTheDocument()
})
