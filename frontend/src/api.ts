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

export type MeshtasticChannel = {
  index: number
  name: string
  display_name: string
  role: string
  recommended: boolean
}

export type MeshtasticConnectionType = 'usb' | 'serial' | 'network'

export type MeshtasticDevice = {
  path: string
  label: string
  connection_type: 'usb' | 'serial'
}

export type MeshtasticSettings = {
  connected: boolean
  node_id: number | null
  connection_type: string | null
  channels: MeshtasticChannel[]
  devices: MeshtasticDevice[]
  connection: {
    connection_type: MeshtasticConnectionType
    endpoint: string
  } | null
  selection: {
    node_id: number
    channel_index: number
    channel_name: string
  } | null
  selection_valid: boolean
  recommended_channel_index: number | null
  node_name: string | null
  firmware_version: string | null
  last_contact: string | null
  mesh_status: 'not_evaluated'
  error: string | null
}

export type SystemRole = 'CLIENT' | 'PRIMARY' | 'BACKUP'

export type SystemSettings = {
  system_name: string
  system_role: SystemRole
  role_status: 'active' | 'experimental'
  meshtastic_node_id: number | null
  primary_authority_node_id: number | null
  app_version: string
  protocol_version: number
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

export function getMeshtasticSettings(): Promise<MeshtasticSettings> {
  return request('/api/settings/meshtastic')
}

export function refreshMeshtasticChannels(): Promise<MeshtasticSettings> {
  return request('/api/settings/meshtastic/refresh', { method: 'POST' })
}

export function refreshMeshtasticDevices(): Promise<MeshtasticSettings> {
  return request('/api/settings/meshtastic/devices/refresh', { method: 'POST' })
}

export function testMeshtasticConnection(
  connectionType: MeshtasticConnectionType,
  endpoint: string,
): Promise<MeshtasticSettings> {
  return request('/api/settings/meshtastic/test', {
    method: 'POST',
    body: JSON.stringify({ connection_type: connectionType, endpoint }),
  })
}

export function selectMeshtasticChannel(
  channelIndex: number,
  channelName: string,
): Promise<MeshtasticSettings> {
  return request('/api/settings/meshtastic/channel', {
    method: 'PUT',
    body: JSON.stringify({ channel_index: channelIndex, channel_name: channelName }),
  })
}

export function getSystemSettings(): Promise<SystemSettings> {
  return request('/api/settings/system')
}

export function updateSystemSettings(
  systemName: string,
  systemRole: SystemRole,
  confirmRoleChange: boolean,
): Promise<SystemSettings> {
  return request('/api/settings/system', {
    method: 'PUT',
    body: JSON.stringify({
      system_name: systemName,
      system_role: systemRole,
      confirm_role_change: confirmRoleChange,
    }),
  })
}
