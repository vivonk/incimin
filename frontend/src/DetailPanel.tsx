import { useEffect, useState } from 'react'
import { listSteps } from './api'
import StepGraph from './StepGraph'
import type { AgentStep, Incident, HypothesisView } from './types'

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

export default function DetailPanel({ incident }: { incident: Incident }) {
  const [tab, setTab] = useState<Tab>('findings')
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    listSteps(incident.id)
      .then((s) => live && setSteps(s))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      live = false
    }
  }, [incident.id])

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
          {incident.status === 'awaiting_approval' ? (
            <>
              <h3>Approval required</h3>
              <p className="dim">
                The agent has paused and is waiting on a decision. Approve/Reject controls land
                with the human-in-the-loop gates.
              </p>
            </>
          ) : (
            <>
              <h3>Recommended next steps</h3>
              <pre className="answer">{incident.final_answer ?? 'No recommendation yet.'}</pre>
              {incident.error && <p className="bad mono">{incident.error}</p>}
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
