export type TrafficEvent = {
  sequence: number; timestamp: string; direction: 'TX' | 'RX'; source: number; destination: number
  channel_name: string | null; channel_index: number | null; portnum: number | null
  transport: string; status: string; packet_id: number | null; payload_size: number
  raw_hex: string | null; message_type: string; message_id: string | null
  correlation_id: string | null; protocol_version: number | null; decode_state: string
  decoded: unknown; parsed_fields: Record<string, unknown>; decode_error: string | null; redacted: boolean
}
export type TrafficSnapshot = {
  session: string; revision: number; oldest: number; capacity: number; events: TrafficEvent[]
  registry: { value: number; name: string; sensitive: boolean }[]
}

export function mergeTraffic(previous: TrafficSnapshot | null, update: TrafficSnapshot): TrafficSnapshot {
  const retained = previous?.session === update.session ? previous.events : []
  const events = new Map(retained.map(event => [event.sequence, event]))
  update.events.forEach(event => events.set(event.sequence, event))
  return { ...update, events: [...events.values()].filter(event => event.sequence >= update.oldest)
    .sort((a, b) => a.sequence - b.sequence).slice(-update.capacity) }
}

export function nodeLabel(node: number) {
  return node === 0xffffffff ? 'ALL' : `!${node.toString(16).padStart(8, '0')}`
}

export function decodedText(event: TrafficEvent): string {
  if (event.redacted) return 'Payload hidden: sensitive or unreviewed message type/version'
  if (event.decode_error) return event.decode_error
  const fields = event.parsed_fields
  if (event.message_type === 'THREAD') return `Titel\n${fields.title ?? '–'}`
  if (event.message_type === 'POST' || event.message_type === 'SYNC_POST') {
    return `Tråd-ID\n${fields.thread_id ?? fields.thread_local_id ?? '–'}\n\nText\n${fields.body ?? '–'}`
  }
  if (event.message_type === 'COMMIT_ACK') return `COMMIT_ACK\nApplikationsmeddelande för ${event.correlation_id}.\nDetta är inte Meshtastic routing ACK.`
  if (Array.isArray(fields.objects)) {
    const refs = fields.objects as { kind: string; id: string }[]
    return `${event.message_type}\n${event.message_type === 'WANT' ? 'Begärda objekt' : 'Inventering'}\n${refs.map(ref => `${ref.kind} ${ref.id}`).join('\n') || '(tom)'}${event.message_type === 'SYNC' ? `\n\nSvar begärt: ${fields.reply_requested ? 'Ja' : 'Nej'}` : ''}`
  }
  return 'Ingen säker avkodning tillgänglig.'
}

export function hexDump(raw: string): string {
  const bytes = raw.match(/.{2}/g) ?? []
  const lines: string[] = []
  for (let offset = 0; offset < bytes.length; offset += 16) {
    const row = bytes.slice(offset, offset + 16)
    const ascii = row.map(byte => { const n = parseInt(byte, 16); return n >= 32 && n <= 126 ? String.fromCharCode(n) : '.' }).join('')
    lines.push(`${offset.toString(16).padStart(4, '0')}  ${row.join(' ').toUpperCase().padEnd(47)}  ${ascii}`)
  }
  return lines.join('\n')
}

export function filterTraffic(events: TrafficEvent[], direction: string, kind: string, search: string) {
  const query = search.trim().toLocaleLowerCase()
  return events.filter(event => (!direction || event.direction === direction) && (!kind || event.message_type === kind)
    && `${nodeLabel(event.source)} ${nodeLabel(event.destination)} ${event.message_type} ${event.message_id ?? ''} ${event.correlation_id ?? ''} ${event.channel_name ?? ''} ${JSON.stringify(event.decoded)}`.toLocaleLowerCase().includes(query))
}
