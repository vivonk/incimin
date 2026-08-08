import { Fragment, useCallback, useEffect, useState } from 'react'
import { listIncidents } from './api'
import DetailPanel from './DetailPanel'
import type { Incident, IncidentStatus } from './types'
import './App.css'

const STATUSES: IncidentStatus[] = [
  'open',
  'agent_running',
  'awaiting_approval',
  'executing_remediation',
  'done',
  'needs_human',
  'orphaned',
  'failed',
]

const SEVERITIES = ['critical', 'warning', 'info']

function firedAt(iso: string): string {
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString(
    undefined,
    { hour: '2-digit', minute: '2-digit' },
  )}`
}

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setIncidents(await listIncidents({ status, severity }))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [status, severity])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="app">
      <header className="bar">
        <h1>Incidents</h1>
        <div className="filters">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button onClick={() => void refresh()} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <p className="error">Could not load incidents: {error}</p>}

      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Severity</th>
            <th>Service</th>
            <th>Alert</th>
            <th>Fired</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <Fragment key={i.id}>
              <tr
                className={selected === i.id ? 'row sel' : 'row'}
                onClick={() => setSelected(selected === i.id ? null : i.id)}
              >
                <td>
                  <span className={`pill s-${i.status}`}>{i.status.replace(/_/g, ' ')}</span>
                  {i.current_step && <span className="step">{i.current_step}</span>}
                </td>
                <td>
                  <span className={`sev sev-${i.severity ?? 'none'}`}>{i.severity ?? '—'}</span>
                </td>
                <td className="mono">{i.service}</td>
                <td>{i.alertname}</td>
                <td className="dim">{firedAt(i.fired_at)}</td>
              </tr>
              {selected === i.id && (
                <tr className="detail-row">
                  <td colSpan={5}>
                    <DetailPanel incident={i} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {incidents.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="empty">
                {loading ? 'Loading…' : 'No incidents match these filters.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
