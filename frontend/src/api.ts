import type { AgentStep, Incident } from './types'

// Phase 12 replaces the fetch mechanism here with an SSE subscription. The shapes
// and the call sites stay; only how the data arrives changes.

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`)
  return res.json() as Promise<T>
}

export function listIncidents(filters: {
  status?: string
  severity?: string
}): Promise<Incident[]> {
  const q = new URLSearchParams()
  if (filters.status) q.set('status', filters.status)
  if (filters.severity) q.set('severity', filters.severity)
  const qs = q.toString()
  return get<Incident[]>(`/api/incidents${qs ? `?${qs}` : ''}`)
}

export function listSteps(incidentId: string): Promise<AgentStep[]> {
  return get<AgentStep[]>(`/api/incidents/${incidentId}/steps`)
}
