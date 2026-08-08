import type { ReactNode } from 'react'
import type { Incident, IncidentStatus } from './types'

/** Statuses shown as sidebar filters, in lifecycle order. Rows are filters rather
 *  than links: a nav item that goes nowhere is worse than no nav item, and status
 *  is how anyone actually navigates a queue of incidents. */
const NAV: { id: IncidentStatus | ''; label: string }[] = [
  { id: '', label: 'All incidents' },
  { id: 'open', label: 'Open' },
  { id: 'agent_running', label: 'Investigating' },
  { id: 'awaiting_approval', label: 'Awaiting approval' },
  { id: 'executing_remediation', label: 'Remediating' },
  { id: 'needs_human', label: 'Needs human' },
  { id: 'done', label: 'Resolved' },
  { id: 'failed', label: 'Failed' },
  { id: 'orphaned', label: 'Orphaned' },
]

export function Banner() {
  return (
    <header className="ic-banner">
      <div className="ic-brand">
        <span className="ic-mark" aria-hidden="true" />
        <span className="ic-word">incimin</span>
        <span className="ic-chip">v1.7</span>
      </div>
      <p className="ic-tagline">
        Autonomous root-cause analysis — every alert, from firing to resolved
      </p>
    </header>
  )
}

export function Sidebar({
  incidents,
  status,
  onStatus,
  connected,
}: {
  incidents: Incident[]
  status: string
  onStatus: (s: string) => void
  connected: boolean
}) {
  const count = (id: string) =>
    id === '' ? incidents.length : incidents.filter((i) => i.status === id).length

  return (
    <aside className="ic-side">
      <nav>
        <p className="ic-navlabel">Incidents</p>
        {NAV.map((n) => {
          const c = count(n.id)
          return (
            <button
              key={n.id || 'all'}
              className={`ic-navitem${status === n.id ? ' on' : ''}`}
              onClick={() => onStatus(n.id)}
            >
              <span className={`ic-dot d-${n.id || 'all'}`} aria-hidden="true" />
              <span className="ic-navtext">{n.label}</span>
              <span className="ic-navcount">{c || ''}</span>
            </button>
          )
        })}
      </nav>

      <div className="ic-sidefoot">
        <span className={`ic-live${connected ? ' on' : ''}`} aria-hidden="true" />
        <div>
          <div className="ic-livetext">{connected ? 'API connected' : 'API unreachable'}</div>
          <div className="ic-livesub">127.0.0.1:8088</div>
        </div>
      </div>
    </aside>
  )
}

export function Card({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="ic-card">
      <div className="ic-cardhead">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

export function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="ic-stat">
      <span className="ic-statnum">{value}</span>
      <span className="ic-statlabel">{label}</span>
    </div>
  )
}

/** Horizontal bars, as in the reference. Counts are small integers here, so the
 *  scale is the max rather than a fixed axis — a fixed axis would make one
 *  incident look like nothing. */
export function BarList({ rows }: { rows: { label: string; value: number }[] }) {
  if (rows.length === 0) return <p className="ic-empty">Nothing recorded yet.</p>
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <ul className="ic-bars">
      {rows.map((r) => (
        <li key={r.label}>
          <span className="ic-barlabel" title={r.label}>
            {r.label}
          </span>
          <span className="ic-bartrack">
            <span className="ic-barfill" style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="ic-barval">{r.value}</span>
        </li>
      ))}
    </ul>
  )
}
