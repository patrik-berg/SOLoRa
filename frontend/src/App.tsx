import { type FormEvent, useEffect, useRef, useState } from 'react'

import {
  createPost,
  createThread,
  getMeshtasticSettings,
  getThread,
  listThreads,
  refreshMeshtasticChannels,
  refreshMeshtasticDevices,
  selectMeshtasticChannel,
  testMeshtasticConnection,
  type MeshtasticConnectionType,
  type MeshtasticSettings,
  type Thread,
  type ThreadSummary,
} from './api.ts'

function formatDate(value: string) {
  return new Intl.DateTimeFormat('sv-SE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function connectionLabel(value: MeshtasticConnectionType | null | undefined) {
  if (value === 'usb') return 'USB'
  if (value === 'serial') return 'Serial'
  if (value === 'network') return 'Network'
  return '–'
}

export default function App() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newPost, setNewPost] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [view, setView] = useState<'forum' | 'settings'>('forum')
  const [radio, setRadio] = useState<MeshtasticSettings | null>(null)
  const [radioLoading, setRadioLoading] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState('')
  const [connectionType, setConnectionType] = useState<MeshtasticConnectionType>('usb')
  const [connectionEndpoint, setConnectionEndpoint] = useState('')
  const threadButtons = useRef(new Map<number, HTMLButtonElement>())

  async function refreshThreads() {
    setThreads(await listThreads())
  }

  function applyRadioStatus(status: MeshtasticSettings) {
    setRadio(status)
    if (status.connection) {
      setConnectionType(status.connection.connection_type)
      setConnectionEndpoint(status.connection.endpoint)
    }
    if (status.selection) {
      setSelectedChannel(`${status.selection.channel_index}:${status.selection.channel_name}`)
    }
  }

  async function openThread(threadId: number) {
    setError('')
    try {
      setSelectedThread(await getThread(threadId))
    } catch {
      setError('Det gick inte att öppna tråden.')
    }
  }

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- the effect synchronizes API data.
    void refreshThreads()
      .catch(() => setError('Det gick inte att läsa trådarna.'))
      .finally(() => setLoading(false))
    void getMeshtasticSettings().then(applyRadioStatus).catch(() => undefined)
  }, [])

  async function handleCreateThread(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!newTitle.trim()) return
    setError('')
    try {
      const thread = await createThread(newTitle)
      setNewTitle('')
      await refreshThreads()
      await openThread(thread.id)
    } catch {
      setError('Det gick inte att skapa tråden.')
    }
  }

  async function handleCreatePost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedThread || !newPost.trim()) return
    setError('')
    try {
      await createPost(selectedThread.id, newPost)
      setNewPost('')
      await openThread(selectedThread.id)
      await refreshThreads()
    } catch {
      setError('Det gick inte att spara inlägget.')
    }
  }

  function closeThread() {
    const threadId = selectedThread?.id
    setSelectedThread(null)
    if (threadId !== undefined) threadButtons.current.get(threadId)?.focus()
  }

  async function openSettings() {
    setView('settings')
    setError('')
    setRadioLoading(true)
    try {
      applyRadioStatus(await getMeshtasticSettings())
    } catch {
      setError('Det gick inte att läsa radioinställningarna.')
    } finally {
      setRadioLoading(false)
    }
  }

  async function refreshDevices() {
    setError('')
    setRadioLoading(true)
    try {
      applyRadioStatus(await refreshMeshtasticDevices())
    } catch {
      setError('Det gick inte att läsa datorns serial-enheter.')
    } finally {
      setRadioLoading(false)
    }
  }

  async function testConnection() {
    if (!connectionEndpoint.trim()) return
    setError('')
    setRadioLoading(true)
    try {
      const status = await testMeshtasticConnection(connectionType, connectionEndpoint.trim())
      applyRadioStatus(status)
      const preferred = status.selection_valid
        ? status.selection?.channel_index
        : status.recommended_channel_index
      const channel = status.channels.find((candidate) => candidate.index === preferred)
      setSelectedChannel(channel ? `${channel.index}:${channel.name}` : '')
    } catch {
      setError('Anslutningstestet misslyckades.')
    } finally {
      setRadioLoading(false)
    }
  }

  async function reconnect() {
    setError('')
    setRadioLoading(true)
    try {
      applyRadioStatus(await refreshMeshtasticChannels())
    } catch {
      setError('Kunde inte återansluta till Meshtastic-noden.')
    } finally {
      setRadioLoading(false)
    }
  }

  async function saveRadioChannel() {
    const separator = selectedChannel.indexOf(':')
    if (separator < 0) return
    setError('')
    setRadioLoading(true)
    try {
      applyRadioStatus(
        await selectMeshtasticChannel(
          Number(selectedChannel.slice(0, separator)),
          selectedChannel.slice(separator + 1),
        ),
      )
    } catch {
      setError('Kanalen har ändrats. Uppdatera listan och bekräfta igen.')
    } finally {
      setRadioLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <header>
        <div>
          <p className="eyebrow">Local forum · Phase 1</p>
          <h1>SOLoRa</h1>
        </div>
        <div className="header-actions">
          <button
            className={radio?.connected ? 'connection-pill online' : 'connection-pill offline'}
            onClick={() => void openSettings()}
            type="button"
          >
            <span aria-hidden="true">●</span>{' '}
            {radio?.connected
              ? `${radio.node_name ?? `0x${radio.node_id?.toString(16)}`} via ${connectionLabel(radio.connection?.connection_type)}`
              : 'Offline'}
          </button>
          <span className="local-badge">Sparas lokalt</span>
        </div>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      {view === 'settings' ? (
        <main className="settings-main">
          <section className="settings-card" aria-busy={radioLoading}>
            <button className="back-button" onClick={() => setView('forum')} type="button">
              <span aria-hidden="true">←</span> Till forumet
            </button>
            <p className="eyebrow">Systeminställningar</p>
            <h2>Meshtastic</h2>
            <p className="settings-intro">
              Välj hur denna dator ansluter till Meshtastic-noden. Ingen terminal eller manuell config behövs.
            </p>

            <fieldset className="connection-types">
              <legend>Anslutningstyp</legend>
              {(['usb', 'serial', 'network'] as MeshtasticConnectionType[]).map((kind) => (
                <label key={kind}>
                  <input
                    checked={connectionType === kind}
                    name="connection-type"
                    onChange={() => {
                      setConnectionType(kind)
                      setConnectionEndpoint('')
                    }}
                    type="radio"
                  />
                  {connectionLabel(kind)}
                </label>
              ))}
            </fieldset>

            {connectionType === 'network' ? (
              <div className="connection-input">
                <label htmlFor="network-host">Hostname eller IP-adress</label>
                <input
                  id="network-host"
                  onChange={(event) => setConnectionEndpoint(event.target.value)}
                  placeholder="meshtastic.local eller 192.168.1.42"
                  value={connectionEndpoint}
                />
              </div>
            ) : (
              <div className="connection-input">
                <label htmlFor="serial-device">Upptäckt enhet</label>
                <select
                  id="serial-device"
                  onChange={(event) => setConnectionEndpoint(event.target.value)}
                  value={connectionEndpoint}
                >
                  <option value="">Välj enhet…</option>
                  {radio?.devices
                    .filter((device) => device.connection_type === connectionType)
                    .map((device) => (
                    <option key={device.path} value={device.path}>
                      {device.label} · {device.path} · {connectionLabel(device.connection_type)}
                    </option>
                    ))}
                </select>
                <button
                  className="secondary-button"
                  disabled={radioLoading}
                  onClick={() => void refreshDevices()}
                  type="button"
                >
                  Uppdatera enhetslista
                </button>
              </div>
            )}

            <button
              disabled={!connectionEndpoint.trim() || radioLoading}
              onClick={() => void testConnection()}
              type="button"
            >
              {radioLoading ? 'Testar…' : 'Testa och spara anslutning'}
            </button>

            <dl className="radio-status">
              <div><dt>Lokal anslutning</dt><dd>{radio?.connected ? '● Online' : '● Offline'}</dd></div>
              <div><dt>Typ</dt><dd>{connectionLabel(radio?.connection?.connection_type)}</dd></div>
              <div><dt>Nod</dt><dd>{radio?.node_name ?? '–'}</dd></div>
              <div><dt>Nod-ID</dt><dd>{radio?.node_id ? `0x${radio.node_id.toString(16).toUpperCase()}` : '–'}</dd></div>
              <div><dt>Firmware</dt><dd>{radio?.firmware_version ?? '–'}</dd></div>
              <div><dt>Senaste kontakt</dt><dd>{radio?.last_contact ? formatDate(radio.last_contact) : '–'}</dd></div>
              <div><dt>Mesh/radio</dt><dd>Ej utvärderad</dd></div>
            </dl>

            {radio?.error && <p className="settings-warning" role="status">{radio.error}</p>}

            {radio?.connection && (
              <button
                className="secondary-button"
                disabled={radioLoading}
                onClick={() => void reconnect()}
                type="button"
              >
                Återanslut med sparad konfiguration
              </button>
            )}

            {radio && radio.channels.length > 0 && (
              <div className="channel-picker">
                <h3>Meshtastic-kanal</h3>
                <p>
                  SOLoRa rekommenderar <strong>solora-link</strong>. Kanalnycklar visas eller sparas aldrig här.
                </p>
                <label htmlFor="meshtastic-channel">SOLoRa-kanal på denna nod</label>
                <select
                  id="meshtastic-channel"
                  onChange={(event) => setSelectedChannel(event.target.value)}
                  value={selectedChannel}
                >
                  <option value="">Välj kanal…</option>
                  {radio.channels.map((channel) => (
                    <option key={channel.index} value={`${channel.index}:${channel.name}`}>
                      {channel.display_name} · index {channel.index} · {channel.role}
                      {channel.recommended ? ' · rekommenderad' : ''}
                    </option>
                  ))}
                </select>
                <button
                  disabled={!selectedChannel || radioLoading}
                  onClick={() => void saveRadioChannel()}
                  type="button"
                >
                  Bekräfta kanal
                </button>
              </div>
            )}
          </section>
        </main>
      ) : (
        <main>
          <aside className="thread-panel">
            <div className="panel-heading"><h2>Trådar</h2><span>{threads.length}</span></div>
            <form className="new-thread" onSubmit={handleCreateThread}>
              <label htmlFor="thread-title">Ny tråd</label>
              <div className="inline-form">
                <input id="thread-title" maxLength={200} onChange={(event) => setNewTitle(event.target.value)} placeholder="Rubrik" value={newTitle} />
                <button type="submit">Skapa</button>
              </div>
            </form>
            <nav aria-label="Forumtrådar">
              {loading && <p className="empty-state">Läser trådar…</p>}
              {!loading && threads.length === 0 && <p className="empty-state">Inga trådar ännu. Skapa den första.</p>}
              {threads.map((thread) => (
                <button className={selectedThread?.id === thread.id ? 'thread-link active' : 'thread-link'} key={thread.id} onClick={() => void openThread(thread.id)} ref={(element) => { if (element) threadButtons.current.set(thread.id, element); else threadButtons.current.delete(thread.id) }} type="button">
                  <strong>{thread.title}</strong><span>{thread.post_count} inlägg</span>
                </button>
              ))}
            </nav>
          </aside>
          <section className="conversation" aria-live="polite">
            {!selectedThread ? (
              <div className="welcome">
                <p className="eyebrow">Redo lokalt</p>
                <h2>Välj en tråd</h2>
                <p>Öppna en tråd till vänster eller skapa en ny för att börja skriva.</p>
                {radio && !radio.connection && (
                  <button className="setup-link" onClick={() => void openSettings()} type="button">
                    Konfigurera Meshtastic
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="conversation-heading">
                  <div><button className="back-button" onClick={closeThread} type="button"><span aria-hidden="true">←</span> Tillbaka till trådar</button><p className="eyebrow">Tråd #{selectedThread.id}</p><h2>{selectedThread.title}</h2></div>
                  <time dateTime={selectedThread.created_at}>{formatDate(selectedThread.created_at)}</time>
                </div>
                <div className="posts">
                  {selectedThread.posts.length === 0 && <p className="empty-state">Tråden har inga inlägg ännu.</p>}
                  {selectedThread.posts.map((post) => <article key={post.id}><p>{post.body}</p><time dateTime={post.created_at}>{formatDate(post.created_at)}</time></article>)}
                </div>
                <form className="new-post" onSubmit={handleCreatePost}>
                  <label htmlFor="post-body">Nytt inlägg</label>
                  <textarea id="post-body" maxLength={4000} onChange={(event) => setNewPost(event.target.value)} placeholder="Skriv något…" rows={4} value={newPost} />
                  <button type="submit">Publicera lokalt</button>
                </form>
              </>
            )}
          </section>
        </main>
      )}

      <footer>Lokal forumdata · Meshstatus visas separat när radio är ansluten</footer>
    </div>
  )
}
