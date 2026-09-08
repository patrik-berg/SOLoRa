import { useEffect, useRef, useState } from 'react'

import { heartbeatAge, type ApplicationStatus } from './applicationStatus.ts'

export default function ApplicationStatusBar({ status }: { status: ApplicationStatus }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [dismissedOutage, setDismissedOutage] = useState(-1)
  const [now, setNow] = useState(() => Date.now())
  const offline = status.state === 'offline'
  const modalOpen = offline && dismissedOutage !== status.outage

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    if (modalOpen && !dialog.current?.open) dialog.current?.showModal()
    if (!modalOpen && dialog.current?.open) dialog.current?.close()
  }, [modalOpen])

  const node = offline ? null : status.summary?.meshtastic
  const connection = node?.connection_type === 'usb' ? 'USB' : node?.connection_type === 'network' ? 'Network' : node?.connection_type === 'serial' ? 'Serial' : null
  const nodeText = node?.connection_state === 'online'
    ? `Online${connection ? ` via ${connection}` : ''}`
    : node?.connection_state === 'offline' ? 'Offline' : 'Unknown'
  const age = offline ? null : heartbeatAge(status.summary?.primary.last_heartbeat_at ?? null, now)
  const applicationLabel = { checking: 'Checking', online: 'Online', degraded: 'Degraded', offline: 'Offline' }[status.state]

  return (
    <>
      <div className="global-status" aria-label="Global systemstatus">
        <span className={`status-item ${status.state}`}><span aria-hidden="true">●</span> Application {applicationLabel}</span>
        <span className={`status-item ${node?.connection_state ?? 'unknown'}`}><span aria-hidden="true">●</span> Node {nodeText}</span>
        <span className="status-item">Primary · {age ? `last heartbeat ${age} ago` : 'Unknown'}</span>
      </div>
      <div className="application-notice" role="status" aria-live="polite">
        {offline && 'SOLoRa är offline. Kontrollerar automatiskt anslutningen.'}
        {status.state === 'degraded' && 'SOLoRa svarar, men applikationen är inte redo. Kontrollera databas, migrations och frontend via kontrollfönstret.'}
        {status.state === 'online' && status.recoveredAt !== null && now - status.recoveredAt < 6000 && 'SOLoRa är online igen.'}
      </div>
      <dialog ref={dialog} className="offline-dialog" aria-labelledby="offline-title" aria-describedby="offline-description" onCancel={() => setDismissedOutage(status.outage)}>
        <h2 id="offline-title">SOLoRa är offline</h2>
        <p id="offline-description">Webbgränssnittet har tappat kontakten med den lokala SOLoRa-applikationen.</p>
        <p>Kontrollerar automatiskt om anslutningen kommer tillbaka.</p>
        <p>Senast online: {status.lastOnline === null ? 'Ingen lyckad kontroll ännu' : new Date(status.lastOnline).toLocaleTimeString('sv-SE')}</p>
        <button type="button" onClick={() => setDismissedOutage(status.outage)}>Fortsätt visa sidan</button>
      </dialog>
    </>
  )
}
