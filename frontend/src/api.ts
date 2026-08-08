import type { AgentStep, Approval, Incident } from './types'

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

export function listApprovals(incidentId: string): Promise<Approval[]> {
  return get<Approval[]>(`/api/incidents/${incidentId}/approvals`)
}

export async function decide(
  incidentId: string,
  decision: 'approved' | 'rejected',
  note?: string,
): Promise<{ status: string }> {
  const res = await fetch(`/api/incidents/${incidentId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note: note || null, decided_by: 'operator' }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    // 409 is the expected answer when someone else already decided this gate —
    // surface it as-is rather than as a generic failure.
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return body
}
