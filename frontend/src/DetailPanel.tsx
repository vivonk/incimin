import { useCallback, useEffect, useState } from 'react'
import { decide, listApprovals, listSteps } from './api'
import StepGraph from './StepGraph'
import type { AgentStep, Approval, Incident, HypothesisView } from './types'

type Tab = 'findings' | 'next' | 'graph' | 'raw'

const TABS: { id: Tab; label: string }[] = [
  { id: 'findings', label: 'Findings' },
  { id: 'next', label: 'Next Steps' },
  { id: 'graph', label: 'Step Graph' },
  { id: 'raw', label: 'Raw' },
]

/** The latest belief state the run reached. Hypotheses are rewritten each round,
 *  so the last step carrying them is the current picture; earlier ones are the
 *  trajectory that got there. */
function latestHypotheses(steps: AgentStep[]): HypothesisView[] {
  for (let i = steps.length - 1; i >= 0; i--) {
    const h = steps[i].output?.hypotheses
    if (h?.length) return h
  }
  return []
}

function verification(steps: AgentStep[]) {
  for (let i = steps.length - 1; i >= 0; i--) {
    const v = steps[i].output?.verification_result
    if (v) return v
  }
  return null
}

function budget(steps: AgentStep[]) {
  for (let i = steps.length - 1; i >= 0; i--) {
    const b = steps[i].output?.budget
    if (b) return b
  }
  return null
}

/** One pending gate, rendered so a human can see exactly what they are agreeing to
 *  before they agree to it — the action, the target, and the reasoning behind it. */
function Gate({
  approval,
  busy,
  error,
  onDecide,
}: {
  approval: Approval
  busy: boolean
  error: string | null
  onDecide: (d: 'approved' | 'rejected', note: string) => void
}) {
  const p = approval.proposal || {}
  const [note, setNote] = useState('')

  return (
    <div className="gate">
      {approval.kind === 'remediation' ? (
        <>
          <p className="gate-action">{p.statement}</p>
          <div className="kv">
            <span>Command</span>
            <strong className="mono">{p.argv?.join(' ')}</strong>
            <span>Why</span>
            <strong>{p.rationale}</strong>
          </div>
        </>
      ) : (
        <>
          <p className="gate-action">
            The agent could not establish a root cause and is asking to hand this on.
          </p>
          <div className="kv">
            {p.best_guess && (
              <>
                <span>Best guess</span>
                <strong>
                  {p.best_guess.statement}{' '}
                  <span className="dim">({p.best_guess.posterior.toFixed(2)})</span>
                </strong>
              </>
            )}
            <span>Failed checks</span>
            <strong className="mono">{(p.failed_checks || []).join(', ') || '—'}</strong>
          </div>
        </>
      )}

      <input
        className="note"
        placeholder="Note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        disabled={busy}
      />
      <div className="gate-actions">
        <button className="approve" disabled={busy} onClick={() => onDecide('approved', note)}>
          {busy ? 'Working…' : 'Approve'}
        </button>
        <button className="reject" disabled={busy} onClick={() => onDecide('rejected', note)}>
          Reject
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}

export default function DetailPanel({ incident }: { incident: Incident }) {
  const [tab, setTab] = useState<Tab>('findings')
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [decideError, setDecideError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([listSteps(incident.id), listApprovals(incident.id)])
      setSteps(s)
      setApprovals(a)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [incident.id])

  useEffect(() => {
    void load()
  }, [load])

  const pending = approvals.find((a) => a.decision === 'pending') ?? null
  const decided = approvals.filter((a) => a.decision !== 'pending')

  async function submit(decision: 'approved' | 'rejected', note: string) {
    setBusy(true)
    setDecideError(null)
    try {
      await decide(incident.id, decision, note)
      // The resume runs in the background; give it a beat before re-reading so the
      // panel shows the outcome rather than the gate it just closed.
      await new Promise((r) => setTimeout(r, 1200))
      await load()
    } catch (e) {
      setDecideError(e instanceof Error ? e.message : String(e))
      await load()
    } finally {
      setBusy(false)
    }
  }

  const hypotheses = latestHypotheses(steps)
  const vr = verification(steps)
  const bud = budget(steps)
  const probes = steps.filter((s) => s.kind === 'tool_result')

  return (
    <div className="detail">
      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={t.id === tab ? 'tab on' : 'tab'}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error && <p className="error">Could not load steps: {error}</p>}

      {tab === 'findings' && (
        <div className="pad">
          <div className="kv">
            <span>Root cause</span>
            <strong>{incident.root_cause_service ?? '— not established'}</strong>
            <span>Confidence</span>
            <strong>{incident.confidence ?? '—'}</strong>
            {bud && (
              <>
                <span>Stopped because</span>
                <strong className="mono">{bud.exit_reason || '—'}</strong>
                <span>Rounds</span>
                <strong>
                  {bud.rounds_used} / {bud.max_rounds}
                </strong>
              </>
            )}
          </div>

          {hypotheses.length > 0 && (
            <>
              <h3>Hypotheses considered</h3>
              <table className="inner">
                <thead>
                  <tr>
                    <th>Posterior</th>
                    <th>Kind</th>
                    <th>Service</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {[...hypotheses]
                    .sort((a, b) => b.posterior - a.posterior)
                    .map((h) => (
                      <tr key={h.id} className={h.status === 'refuted' ? 'refuted' : ''}>
                        <td>
                          <div className="posterior">
                            <div style={{ width: `${Math.round(h.posterior * 100)}%` }} />
                            <span>{h.posterior.toFixed(2)}</span>
                          </div>
                        </td>
                        <td className="mono">{h.kind}</td>
                        <td className="mono">{h.service}</td>
                        <td>{h.status}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </>
          )}

          {probes.length > 0 && (
            <>
              <h3>Evidence gathered</h3>
              <ul className="plain">
                {probes.map((p) => (
                  <li key={p.seq}>
                    <span className="mono">{p.name}</span>
                    <span className="dim"> — {p.output?.summary || p.status}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {vr && (
            <>
              <h3>Verifier</h3>
              <p className={vr.passed ? 'ok' : 'bad'}>{vr.passed ? 'PASSED' : 'FAILED'}</p>
              {vr.failed_checks?.length > 0 && (
                <p className="dim mono">{vr.failed_checks.join(', ')}</p>
              )}
              <p className="dim">{vr.detail}</p>
            </>
          )}
        </div>
      )}

      {tab === 'next' && (
        <div className="pad">
          {pending ? (
            <>
              <h3>{pending.kind === 'remediation' ? 'Approval required' : 'Escalation sign-off'}</h3>
              <Gate
                approval={pending}
                busy={busy}
                error={decideError}
                onDecide={(d, n) => void submit(d, n)}
              />
            </>
          ) : (
            <>
              <h3>Recommended next steps</h3>
              <pre className="answer">{incident.final_answer ?? 'No recommendation yet.'}</pre>
              {incident.error && <p className="bad mono">{incident.error}</p>}
            </>
          )}

          {decided.length > 0 && (
            <>
              <h3>Decision history</h3>
              <ul className="plain">
                {decided.map((a) => (
                  <li key={a.id}>
                    <span className="mono">{a.kind}</span> — <strong>{a.decision}</strong>
                    {a.decided_by && <span className="dim"> by {a.decided_by}</span>}
                    {a.decided_at && (
                      <span className="dim"> · {new Date(a.decided_at).toLocaleString()}</span>
                    )}
                    {a.note && <div className="dim">“{a.note}”</div>}
                    {a.execution_result && (
                      <div className={a.execution_result.ok ? 'ok' : 'bad'}>
                        {a.execution_result.ok ? '✓' : '✗'} {a.execution_result.detail}
                        <span className="dim mono"> ({a.execution_result.argv?.join(' ')})</span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {tab === 'graph' && <StepGraph steps={steps} />}

      {tab === 'raw' && (
        <div className="pad">
          <pre className="answer">{JSON.stringify(incident.raw, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
