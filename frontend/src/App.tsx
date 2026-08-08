import { Fragment, useCallback, useEffect, useState } from 'react'
import { listIncidents } from './api'
import DetailPanel from './DetailPanel'
import { Banner, BarList, Card, Sidebar, Stat } from './Shell'
import type { Incident, IncidentStatus } from './types'
import './App.css'

const SEVERITIES = ['critical', 'warning', 'info']

const STATUS_LABEL: Record<IncidentStatus, string> = {
  open: 'open',
  agent_running: 'investigating',
  awaiting_approval: 'awaiting approval',
  executing_remediation: 'remediating',
  done: 'resolved',
  needs_human: 'needs human',
  orphaned: 'orphaned',
  failed: 'failed',
}

function firedAt(iso: string): string {
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString(
    undefined,
    { hour: '2-digit', minute: '2-digit' },
  )}`
}

function countBy(rows: Incident[], key: (i: Incident) => string) {
  const m = new Map<string, number>()
  for (const r of rows) {
    const k = key(r)
    if (k) m.set(k, (m.get(k) ?? 0) + 1)
  }
  return [...m.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6)
}

export default function App() {
  const [all, setAll] = useState<Incident[]>([])
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  // The unfiltered set is fetched once per refresh and filtered in the browser, so
  // the sidebar can show a count for every status at the same time as the table
  // shows one of them. Server-side filtering would need a request per count.
  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setAll(await listIncidents({}))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const visible = all.filter(
    (i) => (!status || i.status === status) && (!severity || i.severity === severity),
  )

  const awaiting = all.filter((i) => i.status === 'awaiting_approval').length
  const active = all.filter(
    (i) => i.status === 'agent_running' || i.status === 'executing_remediation',
  ).length

  // Only finished runs count toward the outcome rate — an incident still being
  // investigated has not failed to find a cause, it just has not finished.
  const settled = all.filter((i) =>
    ['done', 'needs_human', 'failed'].includes(i.status),
  ).length
  const withCause = all.filter((i) => i.root_cause_service).length
  const resolvedPct = settled === 0 ? 0 : Math.round((withCause / settled) * 100)

  return (
    <div className="ic-app">
      <Banner />
      <div className="ic-body">
        <Sidebar
          incidents={all}
          status={status}
          onStatus={setStatus}
          connected={error === null}
        />

        <main className="ic-main">
          <div className="ic-topbar">
            <h1>{status ? STATUS_LABEL[status as IncidentStatus] : 'All incidents'}</h1>
            <div className="ic-controls">
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
          </div>

          {error && (
            <p className="ic-error">
              Could not reach the API: {error}. Start it with{' '}
              <code>uv run uvicorn src.api.main:app --port 8088</code>.
            </p>
          )}

          <div className="ic-grid">
            <Card title="Incidents">
              <Stat value={all.length} label="total received" />
              <BarList rows={countBy(all, (i) => i.service)} />
            </Card>

            <Card title="Needs attention">
              <Stat value={awaiting} label="awaiting a decision" />
              <div className="ic-substat">
                <span>{active} investigating now</span>
                <span>{all.filter((i) => i.status === 'needs_human').length} handed to a human</span>
                <span>{all.filter((i) => i.status === 'failed').length} failed</span>
              </div>
            </Card>

            {/* The question the product exists to answer: did the agent get to a
                cause on its own, or did it hand the incident back? */}
            <Card title="Agent outcome">
              <Stat value={`${resolvedPct}%`} label="reached a root cause" />
              <BarList
                rows={[
                  { label: 'root cause', value: withCause },
                  { label: 'escalated', value: settled - withCause },
                ].filter((r) => r.value > 0)}
              />
            </Card>
          </div>

          <Card
            title={`${visible.length} incident${visible.length === 1 ? '' : 's'}`}
            action={
              status || severity ? (
                <button
                  className="ic-clear"
                  onClick={() => {
                    setStatus('')
                    setSeverity('')
                  }}
                >
                  Clear filters
                </button>
              ) : null
            }
          >
            <table className="ic-table">
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
                {visible.map((i) => (
                  <Fragment key={i.id}>
                    <tr
                      className={selected === i.id ? 'ic-row sel' : 'ic-row'}
                      onClick={() => setSelected(selected === i.id ? null : i.id)}
                    >
                      <td>
                        <span className={`ic-pill s-${i.status}`}>{STATUS_LABEL[i.status]}</span>
                        {i.current_step && <span className="ic-step">{i.current_step}</span>}
                      </td>
                      <td>
                        <span className={`ic-sev sev-${i.severity ?? 'none'}`}>
                          {i.severity ?? '—'}
                        </span>
                      </td>
                      <td className="mono">{i.service}</td>
                      <td>{i.alertname}</td>
                      <td className="dim">{firedAt(i.fired_at)}</td>
                    </tr>
                    {selected === i.id && (
                      <tr className="ic-detailrow">
                        <td colSpan={5}>
                          <DetailPanel incident={i} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {visible.length === 0 && !error && (
                  <tr>
                    <td colSpan={5} className="ic-empty">
                      {loading
                        ? 'Loading…'
                        : all.length === 0
                          ? 'No incidents yet. Post an alert to /webhook/signoz to see one here.'
                          : 'No incidents match these filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Card>
        </main>
      </div>
    </div>
  )
}
