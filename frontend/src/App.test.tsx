import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App.tsx'

const thread = {
  id: 1,
  title: 'Första tråden',
  created_at: '2026-09-07T12:00:00',
  post_count: 1,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('lists and opens a local thread', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const path = String(input)
    const body = path === '/api/threads' ? [thread] : { ...thread, posts: [] }
    return new Response(JSON.stringify(body), {
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  render(<App />)

  const threadButton = await screen.findByRole('button', { name: /Första tråden/ })
  fireEvent.click(threadButton)

  expect(await screen.findByRole('heading', { name: 'Första tråden' })).toBeInTheDocument()
  expect(screen.getByText('Tråden har inga inlägg ännu.')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Tillbaka till trådar' }))

  expect(screen.getByRole('heading', { name: 'Välj en tråd' })).toBeInTheDocument()
  expect(threadButton).toHaveFocus()
})

test('shows loading and empty states', async () => {
  let resolveThreads: ((response: Response) => void) | undefined
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveThreads = resolve
        }),
    ),
  )

  render(<App />)

  expect(screen.getByText('Läser trådar…')).toBeInTheDocument()
  resolveThreads?.(Response.json([]))
  expect(await screen.findByText('Inga trådar ännu. Skapa den första.')).toBeInTheDocument()
})

test('creates a thread and a post', async () => {
  const requests: Array<{ path: string; method: string }> = []
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = String(input)
    const method = init?.method ?? 'GET'
    requests.push({ path, method })

    if (path.endsWith('/posts')) {
      return Response.json({
        id: 1,
        thread_id: 2,
        body: 'Lokalt svar',
        created_at: '2026-09-07T12:02:00',
      })
    }
    if (path === '/api/threads' && method === 'POST') {
      return Response.json({ ...thread, id: 2, title: 'Ny tråd', post_count: 0 })
    }
    if (path === '/api/threads/2') {
      const hasPost = requests.some((request) => request.path.endsWith('/posts'))
      return Response.json({
        ...thread,
        id: 2,
        title: 'Ny tråd',
        post_count: hasPost ? 1 : 0,
        posts: hasPost
          ? [{ id: 1, thread_id: 2, body: 'Lokalt svar', created_at: '2026-09-07T12:02:00' }]
          : [],
      })
    }
    return Response.json(requests.some((request) => request.method === 'POST') ? [] : [])
  })
  vi.stubGlobal('fetch', fetchMock)

  render(<App />)
  await screen.findByText('Inga trådar ännu. Skapa den första.')

  fireEvent.change(screen.getByLabelText('Ny tråd'), { target: { value: 'Ny tråd' } })
  fireEvent.click(screen.getByRole('button', { name: 'Skapa' }))
  await screen.findByRole('heading', { name: 'Ny tråd' })

  fireEvent.change(screen.getByLabelText('Nytt inlägg'), { target: { value: 'Lokalt svar' } })
  fireEvent.click(screen.getByRole('button', { name: 'Publicera lokalt' }))

  expect(await screen.findByText('Lokalt svar')).toBeInTheDocument()
  await waitFor(() => {
    expect(requests).toContainEqual({ path: '/api/threads/2/posts', method: 'POST' })
  })
})

test('shows an error when the API is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Det gick inte att läsa trådarna.')
})
