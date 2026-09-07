export type ThreadSummary = {
  id: number
  title: string
  created_at: string
  post_count: number
}

export type Post = {
  id: number
  message_id: string
  thread_id: number
  body: string
  created_at: string
}

export type Thread = ThreadSummary & {
  posts: Post[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function listThreads(): Promise<ThreadSummary[]> {
  return request('/api/threads')
}

export function getThread(threadId: number): Promise<Thread> {
  return request(`/api/threads/${threadId}`)
}

export function createThread(title: string): Promise<ThreadSummary> {
  return request('/api/threads', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export function createPost(threadId: number, body: string): Promise<Post> {
  return request(`/api/threads/${threadId}/posts`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}
