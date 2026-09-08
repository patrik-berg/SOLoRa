import { useEffect, useState } from 'react'

export type ApplicationState = 'checking' | 'online' | 'degraded' | 'offline'
export type StatusSummary = {
  application: { state: 'online' | 'degraded'; version: string }
  system: { name: string; role: string } | null
  meshtastic: { connection_state: 'online' | 'offline' | 'unknown'; connection_type: string | null; node_id: number | null }
  primary: { node_id: number | null; system_name: string | null; last_heartbeat_at: string | null }
}
export type ApplicationStatus = {
  state: ApplicationState
  summary: StatusSummary | null
  lastOnline: number | null
  recoveredAt: number | null
  outage: number
}

export const STATUS_INTERVAL = 4000
export const STATUS_TIMEOUT = 2500

// Treat a reachable but incompatible/malformed response as degraded, not transport-offline.
function validSummary(value: unknown): value is StatusSummary {
  if (!value || typeof value !== 'object') return false
  const summary = value as Partial<StatusSummary>
  return Boolean(summary.application
    && ['online', 'degraded'].includes(summary.application.state)
    && typeof summary.application.version === 'string'
    && summary.meshtastic
    && ['online', 'offline', 'unknown'].includes(summary.meshtastic.connection_state)
    && (summary.meshtastic.connection_type === null || typeof summary.meshtastic.connection_type === 'string')
    && summary.primary
    && (summary.primary.last_heartbeat_at === null || typeof summary.primary.last_heartbeat_at === 'string'))
}

export function useApplicationStatus(): ApplicationStatus {
  const [status, setStatus] = useState<ApplicationStatus>({ state: 'checking', summary: null, lastOnline: null, recoveredAt: null, outage: 0 })

  useEffect(() => {
    let disposed = false
    let failures = 0
    let recoveryPending = false
    let schedule: ReturnType<typeof setTimeout>
    let request: AbortController | null = null

    async function poll() {
      request = new AbortController()
      const timeout = setTimeout(() => request?.abort(), STATUS_TIMEOUT)
      let received = false
      try {
        const response = await fetch('/api/status', { signal: request.signal, cache: 'no-store' })
        received = true
        const body: unknown = response.ok ? await response.json() : null
        if (disposed) return
        const summary = validSummary(body) ? body : null
        failures = 0
        const state = summary?.application.state ?? 'degraded'
        const recovered = state === 'online' && recoveryPending
        if (recovered) recoveryPending = false
        setStatus(previous => ({ ...previous, state, summary,
          lastOnline: state === 'online' ? Date.now() : previous.lastOnline,
          recoveredAt: recovered ? Date.now() : previous.recoveredAt,
        }))
      } catch {
        if (disposed) return
        // A stalled/aborted response body is a timeout too, not a healthy response.
        const reachable = received && !request.signal.aborted
        failures = reachable ? 0 : failures + 1
        if (failures >= 2) recoveryPending = true
        setStatus(previous => {
          const state = reachable ? 'degraded' : failures >= 2 ? 'offline' : previous.state
          return { ...previous, state, summary: null,
            outage: previous.outage + (state === 'offline' && previous.state !== 'offline' ? 1 : 0),
          }
        })
      } finally {
        clearTimeout(timeout)
        if (!disposed) schedule = setTimeout(() => void poll(), STATUS_INTERVAL)
      }
    }
    void poll()
    return () => { disposed = true; clearTimeout(schedule); request?.abort() }
  }, [])
  return status
}

export function heartbeatAge(timestamp: string | null, now: number): string | null {
  if (!timestamp) return null
  const then = Date.parse(timestamp)
  if (!Number.isFinite(then)) return null
  const seconds = Math.max(0, Math.floor((now - then) / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}
