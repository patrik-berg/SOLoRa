import { useEffect, useRef, useState } from 'react'

import { decodedText, filterTraffic, hexDump, mergeTraffic, nodeLabel, type TrafficEvent, type TrafficSnapshot } from './traffic.ts'

export default function TrafficLog({ offline, channel }: { offline: boolean; channel: string | null }) {
  const [snapshot, setSnapshot] = useState<TrafficSnapshot | null>(null)
  const latest = useRef<TrafficSnapshot | null>(null)
  const pausedRef = useRef(false)
  const [paused, setPaused] = useState(false)
  const [streamState, setStreamState] = useState('Ansluter loggström…')
  const [direction, setDirection] = useState('')
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<TrafficEvent | null>(null)
  const [tab, setTab] = useState('Avkodad')
  const [notice, setNotice] = useState('')
  const [clearing, setClearing] = useState(false)
  const clearFence = useRef(0)

  useEffect(() => {
    if (offline) return
    const source = new EventSource('/api/traffic/stream')
    source.addEventListener('traffic', (message) => {
      try {
        const update = JSON.parse((message as MessageEvent<string>).data) as TrafficSnapshot
        if (!Array.isArray(update.events) || !Array.isArray(update.registry) || !Number.isInteger(update.revision)) throw new Error('Invalid stream')
        if (latest.current?.session === update.session && update.revision < clearFence.current) return
        const sessionChanged = latest.current?.session !== update.session
        if (sessionChanged) clearFence.current = 0
        latest.current = mergeTraffic(latest.current, update)
        if (!pausedRef.current) {
          setSnapshot(latest.current)
          setSelected(previous => !sessionChanged && previous && latest.current?.events.some(event => event.sequence === previous.sequence) ? previous : null)
        }
        setStreamState('Live · passiv observation')
      } catch { setStreamState('Loggströmmen kunde inte läsas') }
    })
    source.onerror = () => setStreamState('Loggström avbruten · återansluter automatiskt')
    return () => source.close()
  }, [offline])

  function togglePause() {
    pausedRef.current = !pausedRef.current
    setPaused(pausedRef.current)
    if (!pausedRef.current) {
      setSnapshot(latest.current)
      setSelected(previous => snapshot?.session === latest.current?.session && previous && latest.current?.events.some(event => event.sequence === previous.sequence) ? previous : null)
    }
  }

  async function clear() {
    if (!window.confirm('Rensa trafikloggen för alla vyer i denna runtime? Forumdata och outbox påverkas inte.')) return
    setClearing(true)
    try {
      const response = await fetch('/api/traffic', { method: 'DELETE' })
      if (!response.ok) throw new Error('Clear failed')
      const update = await response.json() as TrafficSnapshot
      clearFence.current = update.revision
      latest.current = update
      setSnapshot(update); setSelected(null); setNotice('Diagnostikbufferten är rensad.')
    } catch { setNotice('Kunde inte rensa trafikloggen. Försök igen när applikationen är tillgänglig.') }
    finally { setClearing(false) }
  }

  async function exportLog() {
    try {
      const response = await fetch('/api/traffic/export', { cache: 'no-store' })
      if (!response.ok) throw new Error('Export failed')
      const blob = new Blob([JSON.stringify(await response.json(), null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = `solora-traffic-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('JSON-exporten innehåller hela aktuell serverbuffert, inte bara filtrerade rader. Hantera forumtext som privat.')
    } catch { setNotice('Kunde inte exportera trafikloggen.') }
  }

  async function copyHex() {
    if (selected?.raw_hex == null) return
    try { await navigator.clipboard.writeText(hexDump(selected.raw_hex)); setNotice('HEX kopierad.') }
    catch { setNotice('Kunde inte kopiera. Markera och kopiera HEX manuellt.') }
  }

  const rows = filterTraffic(snapshot?.events ?? [], direction, kind, search).reverse()
  return <main className="traffic-main">
    <section className="traffic-workspace" aria-label="Trafiklogg">
      <div className="traffic-heading"><div><p className="eyebrow">Diagnostics · PRIVATE_APP</p><h2>Trafiklogg</h2>
        <p>Visar SOLoRa-frames som skickas och tas emot på vald lokal kanal. Loggen skapar aldrig radiotrafik.</p></div>
        <span className="local-badge">{snapshot?.events.length ?? 0} / {snapshot?.capacity ?? 1000}</span></div>
      <div className="traffic-toolbar">
        <div className="traffic-directions" role="group" aria-label="Riktning">{[['', 'Alla'], ['TX', 'TX'], ['RX', 'RX']].map(([value, label]) =>
          <button key={label} type="button" aria-pressed={direction === value} onClick={() => setDirection(value)}>{label}</button>)}</div>
        <label>Meddelandetyp<select value={kind} onChange={event => setKind(event.target.value)}><option value="">Alla typer</option>
          {snapshot?.registry.map(entry => <option key={entry.value}>{entry.name}</option>)}</select></label>
        <label>Sök i loggen<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Nod, ID eller text…" /></label>
        <button type="button" aria-pressed={paused} onClick={togglePause}>{paused ? 'Fortsätt' : 'Pausa'}</button>
        <button type="button" disabled={offline || clearing} onClick={() => void clear()}>Rensa</button>
        <button type="button" disabled={offline} onClick={() => void exportLog()}>Exportera</button>
      </div>
      <p className="traffic-context">Kanal: <strong>{channel || 'Ingen vald'}</strong> · {paused ? 'Visning pausad · radion fortsätter' : offline ? 'Application Offline · sparad vy' : streamState}</p>
      <p role="status">{notice}</p>
      <div className="traffic-columns">
        <div className="traffic-list">
          <table><caption className="sr-only">Observerade SOLoRa-paket, nyast först</caption><thead><tr>
            {['Tid', 'Riktning', 'Typ', 'Källa → Destination', 'Kanal', 'Storlek', 'Status'].map(label => <th key={label} scope="col">{label}</th>)}
          </tr></thead><tbody>{rows.map(event => <tr key={event.sequence} className={selected?.sequence === event.sequence ? 'selected' : ''}>
            <td data-label="Tid"><button type="button" className="packet-open" aria-label={`Öppna paket ${event.sequence}`} onClick={() => { setSelected(event); setTab('Avkodad') }}><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString('sv-SE')}</time></button></td>
            <td data-label="Riktning"><span className={`traffic-direction ${event.direction.toLowerCase()}`}>{event.direction}</span></td>
            <td data-label="Typ">{event.message_type}</td><td data-label="Noder" className="node-route">{nodeLabel(event.source)} → {nodeLabel(event.destination)}</td>
            <td data-label="Kanal">{event.channel_name || (event.transport === 'in-memory' ? 'Virtuell' : 'Namnlös')} {event.channel_index !== null && `· ${event.channel_index}`}</td>
            <td data-label="Storlek">{event.payload_size} B</td><td data-label="Status">{event.decode_state === 'error' ? 'Decode error' : event.redacted ? 'Hidden' : event.status}</td>
          </tr>)}</tbody></table>
          {rows.length === 0 && <p className="empty-state">{snapshot ? 'Inga matchande paket. Loggen väntar passivt på riktig transporttrafik; lokala foruminlägg skickas inte automatiskt.' : 'Väntar på lokal loggström…'}</p>}
        </div>
        <aside className="packet-details" aria-label="Paketdetaljer"><h3>Paketdetaljer</h3>{!selected ? <p>Välj tiden på en rad för att granska ett paket.</p> : <>
          <dl>{Object.entries({ Riktning: selected.direction, Typ: selected.message_type, Protokoll: selected.protocol_version ?? 'Unknown', 'Message ID': selected.message_id ?? 'Hidden', 'Correlation ID': selected.correlation_id ?? 'Hidden', Källa: nodeLabel(selected.source), Destination: nodeLabel(selected.destination), Kanal: `${selected.channel_name ?? '–'} · index ${selected.channel_index ?? '–'}`, PortNum: selected.portnum ?? 'Virtuell', Storlek: `${selected.payload_size} bytes`, Tid: selected.timestamp, Transport: `${selected.transport} · ${selected.status}`, 'SDK packet ID': selected.packet_id ?? '–' }).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
          <p className="traffic-context">Sent = accepterat av lokal transport, inte bevis på leverans. COMMIT_ACK är applikationstrafik, aldrig routing ACK.</p>
          <div className="detail-tabs" role="group" aria-label="Detaljvy">{['Avkodad', 'HEX', 'Parsing'].map(value => <button type="button" key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{value}</button>)}</div>
          {selected.decode_error && <p className="error">{selected.decode_error}</p>}
          {tab === 'HEX' ? <><button type="button" disabled={selected.raw_hex === null} onClick={() => void copyHex()}>Kopiera HEX</button><pre tabIndex={0} aria-label="Raw HEX">{selected.raw_hex === null ? 'Payload hidden: sensitive or unreviewed message type/version' : hexDump(selected.raw_hex)}</pre></>
            : <pre className={tab === 'Avkodad' ? 'decoded-text' : ''} tabIndex={0} aria-label={tab}>{tab === 'Avkodad' || selected.redacted ? decodedText(selected) : JSON.stringify({ protocol_version: selected.protocol_version, message_type: selected.message_type, message_id: selected.message_id, correlation_id: selected.correlation_id, payload: selected.parsed_fields }, null, 2)}</pre>}
        </>}</aside>
      </div>
    </section>
  </main>
}
