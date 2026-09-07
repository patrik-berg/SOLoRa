import { type FormEvent, useEffect, useRef, useState } from 'react'

import {
  createPost,
  createThread,
  getThread,
  listThreads,
  type Thread,
  type ThreadSummary,
} from './api.ts'

function formatDate(value: string) {
  return new Intl.DateTimeFormat('sv-SE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default function App() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newPost, setNewPost] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const threadButtons = useRef(new Map<number, HTMLButtonElement>())

  async function refreshThreads() {
    setThreads(await listThreads())
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

  return (
    <div className="app-shell">
      <header>
        <div>
          <p className="eyebrow">Local forum · Phase 1</p>
          <h1>SOLoRa</h1>
        </div>
        <span className="local-badge">Sparas lokalt</span>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      <main>
        <aside className="thread-panel">
          <div className="panel-heading">
            <h2>Trådar</h2>
            <span>{threads.length}</span>
          </div>

          <form className="new-thread" onSubmit={handleCreateThread}>
            <label htmlFor="thread-title">Ny tråd</label>
            <div className="inline-form">
              <input
                id="thread-title"
                maxLength={200}
                onChange={(event) => setNewTitle(event.target.value)}
                placeholder="Rubrik"
                value={newTitle}
              />
              <button type="submit">Skapa</button>
            </div>
          </form>

          <nav aria-label="Forumtrådar">
            {loading && <p className="empty-state">Läser trådar…</p>}
            {!loading && threads.length === 0 && (
              <p className="empty-state">Inga trådar ännu. Skapa den första.</p>
            )}
            {threads.map((thread) => (
              <button
                className={selectedThread?.id === thread.id ? 'thread-link active' : 'thread-link'}
                key={thread.id}
                onClick={() => void openThread(thread.id)}
                ref={(element) => {
                  if (element) threadButtons.current.set(thread.id, element)
                  else threadButtons.current.delete(thread.id)
                }}
                type="button"
              >
                <strong>{thread.title}</strong>
                <span>{thread.post_count} inlägg</span>
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
            </div>
          ) : (
            <>
              <div className="conversation-heading">
                <div>
                  <button className="back-button" onClick={closeThread} type="button">
                    <span aria-hidden="true">←</span> Tillbaka till trådar
                  </button>
                  <p className="eyebrow">Tråd #{selectedThread.id}</p>
                  <h2>{selectedThread.title}</h2>
                </div>
                <time dateTime={selectedThread.created_at}>
                  {formatDate(selectedThread.created_at)}
                </time>
              </div>

              <div className="posts">
                {selectedThread.posts.length === 0 && (
                  <p className="empty-state">Tråden har inga inlägg ännu.</p>
                )}
                {selectedThread.posts.map((post) => (
                  <article key={post.id}>
                    <p>{post.body}</p>
                    <time dateTime={post.created_at}>{formatDate(post.created_at)}</time>
                  </article>
                ))}
              </div>

              <form className="new-post" onSubmit={handleCreatePost}>
                <label htmlFor="post-body">Nytt inlägg</label>
                <textarea
                  id="post-body"
                  maxLength={4000}
                  onChange={(event) => setNewPost(event.target.value)}
                  placeholder="Skriv något…"
                  rows={4}
                  value={newPost}
                />
                <button type="submit">Publicera lokalt</button>
              </form>
            </>
          )}
        </section>
      </main>

      <footer>Ingen radioanslutning · Ingen molnsynk</footer>
    </div>
  )
}
