import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App.tsx'

const thread = {
  id: 1,
  title: 'Första tråden',
  created_at: '2026-09-07T12:00:00',
  post_count: 1,
}

const baseStatus = {
  connected: false,
  node_id: null,
  connection_type: null,
  channels: [],
  devices: [],
  connection: null,
  selection: null,
  selection_valid: false,
  recommended_channel_index: null,
  node_name: null,
  firmware_version: null,
  last_contact: null,
  mesh_status: 'not_evaluated',
  error: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('lists and opens a local thread', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const path = String(input)
    const body = path === '/api/threads'
      ? [thread]
      : path === '/api/settings/meshtastic'
        ? baseStatus
        : { ...thread, posts: [] }
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
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    if (String(input) === '/api/settings/meshtastic') return Promise.resolve(Response.json(baseStatus))
    return new Promise<Response>((resolve) => { resolveThreads = resolve })
  }))

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
        message_id: '000000000000000000000001',
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
          ? [{ id: 1, message_id: '000000000000000000000001', thread_id: 2, body: 'Lokalt svar', created_at: '2026-09-07T12:02:00' }]
          : [],
      })
    }
    if (path === '/api/settings/meshtastic') return Response.json(baseStatus)
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

test('refreshes and confirms a Meshtastic channel only from settings', async () => {
  const requests: Array<{ path: string; method: string }> = []
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = String(input)
    const method = init?.method ?? 'GET'
    requests.push({ path, method })
    if (path === '/api/threads') return Response.json([])
    if (path.endsWith('/devices/refresh')) {
      return Response.json({
        ...baseStatus,
        devices: [{ path: 'COM7', label: 'Meshtastic USB', connection_type: 'usb' }],
      })
    }
    if (path.endsWith('/test')) {
      return Response.json({
        ...baseStatus,
        connected: true,
        node_id: 161,
        connection_type: 'serial',
        connection: { connection_type: 'usb', endpoint: 'COM7' },
        node_name: 'SOL7',
        firmware_version: '2.7.22',
        last_contact: '2026-09-08T12:00:00',
        channels: [{ index: 3, name: 'solora-link', display_name: 'solora-link', role: 'secondary', recommended: true }],
        recommended_channel_index: 3,
        error: 'Choose and confirm a SOLoRa channel',
      })
    }
    if (path.endsWith('/channel')) {
      return Response.json({
        ...baseStatus,
        connected: true,
        node_id: 161,
        connection_type: 'serial',
        connection: { connection_type: 'usb', endpoint: 'COM7' },
        node_name: 'SOL7',
        selection: { node_id: 161, channel_index: 3, channel_name: 'solora-link' },
        selection_valid: true,
      })
    }
    return Response.json(baseStatus)
  }))

  render(<App />)
  await screen.findByText('Inga trådar ännu. Skapa den första.')
  expect(requests).toContainEqual({ path: '/api/threads', method: 'GET' })
  expect(requests).toContainEqual({ path: '/api/settings/meshtastic', method: 'GET' })
  expect(requests).toHaveLength(2)

  fireEvent.click(screen.getByRole('button', { name: 'Offline' }))
  await screen.findByRole('heading', { name: 'Meshtastic' })
  fireEvent.click(screen.getByRole('button', { name: 'Uppdatera enhetslista' }))
  const device = await screen.findByLabelText('Upptäckt enhet')
  fireEvent.change(device, { target: { value: 'COM7' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Testa och spara anslutning' }))
  const select = await screen.findByLabelText('SOLoRa-kanal på denna nod')
  expect(select).toHaveValue('3:solora-link')
  expect(screen.getByText('● Online')).toBeInTheDocument()
  expect(screen.getByText('SOL7')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Bekräfta kanal' }))

  await waitFor(() => expect(requests).toContainEqual({ path: '/api/settings/meshtastic/channel', method: 'PUT' }))
  expect(requests).toContainEqual({ path: '/api/settings/meshtastic/devices/refresh', method: 'POST' })
  expect(requests).toContainEqual({ path: '/api/settings/meshtastic/test', method: 'POST' })
  expect(requests).toContainEqual({ path: '/api/settings/meshtastic/channel', method: 'PUT' })
})

test('accepts a network hostname without terminal configuration', async () => {
  let submittedBody = ''
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = String(input)
    if (path === '/api/threads') return Response.json([])
    if (path.endsWith('/test')) {
      submittedBody = String(init?.body)
      return Response.json({
        ...baseStatus,
        connected: true,
        node_id: 178,
        node_name: 'SOL8',
        connection_type: 'network',
        connection: { connection_type: 'network', endpoint: 'mesh.local' },
      })
    }
    return Response.json(baseStatus)
  }))

  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Offline' }))
  fireEvent.click(screen.getByLabelText('Network'))
  fireEvent.change(screen.getByLabelText('Hostname eller IP-adress'), {
    target: { value: 'mesh.local' },
  })
  fireEvent.click(await screen.findByRole('button', { name: 'Testa och spara anslutning' }))

  expect(await screen.findByText('SOL8')).toBeInTheDocument()
  expect(JSON.parse(submittedBody)).toEqual({
    connection_type: 'network',
    endpoint: 'mesh.local',
  })
})
