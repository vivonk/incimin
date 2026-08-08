import { useMemo } from 'react'
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'
import type { AgentStep } from './types'

// The graph is derived from what actually ran, not from a fixed diagram of the
// kernel. Probe fan-out, extra belief rounds, and which exit was taken all vary
// per incident, and those differences are the interesting part.
//
// Every kernel node is one of five narrative stages, in the order they run:
// Meta-Agent gathers evidence and establishes candidates, Hypothesis Generation
// proposes explanations (calling every MCP tool the incimin-sre server exposes
// as part of that), Probe Agent gathers targeted evidence for the leading
// hypotheses, Converge folds evidence into belief and checks it, and Root Cause
// & Next Steps reports the outcome and, if warranted, proposes and gates a fix.
// Coloring and relabeling nodes by stage — rather than by their raw kernel node
// name — is what makes that sequence readable at a glance; a computed
// background band per stage was tried and dropped, because a multi-round run
// loops back through Probe Agent and Converge, and a single band can't
// represent a stage that recurs non-contiguously down the page.

type Stage = 'meta' | 'hypothesis' | 'probe' | 'converge' | 'result'

const STAGE_ORDER: Stage[] = ['meta', 'hypothesis', 'probe', 'converge', 'result']

const STAGE_LABEL: Record<Stage, string> = {
  meta: 'Meta-Agent',
  hypothesis: 'Hypothesis Generation',
  probe: 'Probe Agent',
  converge: 'Converge',
  result: 'Root Cause & Next Steps',
}

// Reuses the app's existing palette tokens so stage colors stay consistent with
// the rest of the UI rather than introducing a second, unrelated color scale.
const STAGE_VAR: Record<Stage, string> = {
  meta: 'var(--info)',
  hypothesis: 'var(--wait)',
  probe: 'var(--warn)',
  converge: 'var(--accent)',
  result: 'var(--ok)',
}

const NODE_STAGE: Record<string, Stage> = {
  ground: 'meta',
  seed: 'hypothesis',
  probe: 'probe',
  update_beliefs: 'converge',
  verify: 'converge',
  report: 'result',
  graceful_exit: 'result',
  propose_remediation: 'result',
  await_approval: 'result',
  execute_remediation: 'result',
  await_escalation: 'result',
}

const FRIENDLY_LABEL: Record<string, string> = {
  ground: 'Meta-Agent',
  seed: 'Hypothesis Generation',
  probe: 'Probe Agent',
  update_beliefs: 'Update Beliefs',
  verify: 'Verify',
  report: 'Root Cause',
  graceful_exit: 'No Root Cause Found',
  propose_remediation: 'Propose Fix',
  await_approval: 'Await Approval',
  execute_remediation: 'Remediation Executed',
  await_escalation: 'Escalation Sign-off',
}

const W = 200
const H = 50

function StepNode({ data }: NodeProps) {
  const d = data as unknown as {
    label: string
    sub?: string
    stage: Stage
    status: string
    title: string
  }
  return (
    <div
      className={`gnode st-${d.status}`}
      style={{ borderLeftColor: STAGE_VAR[d.stage] }}
      title={d.title}
    >
      <Handle type="target" position={Position.Top} />
      <div className="gnode-label">{d.label}</div>
      {d.sub && <div className="gnode-sub">{d.sub}</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

const nodeTypes = { step: StepNode }

/** Dagre layout. Node ids are the step seq, which is stable across refetches —
 *  an index or a generated id would remount every node on each poll. */
function layout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 28, ranksep: 44 })

  nodes.forEach((n) => g.setNode(n.id, { width: W, height: H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)

  return nodes.map((n) => {
    const p = g.node(n.id)
    return { ...n, position: { x: p.x - W / 2, y: p.y - H / 2 } }
  })
}

function Legend() {
  return (
    <div className="glegend">
      {STAGE_ORDER.map((s, i) => (
        <span key={s} className="glegend-item">
          <span className="glegend-dot" style={{ background: STAGE_VAR[s] }} />
          {STAGE_LABEL[s]}
          {i < STAGE_ORDER.length - 1 && <span className="glegend-arrow">→</span>}
        </span>
      ))}
    </div>
  )
}

export default function StepGraph({ steps }: { steps: AgentStep[] }) {
  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = []
    const es: Edge[] = []

    // `node` rows form the spine in execution order; anything with a parent_seq
    // (probe results, tool calls — including the MCP calls hypothesis
    // generation makes) hangs off the node that produced it and inherits its
    // stage, so e.g. `mcp.get_service_topology` reads as part of Hypothesis
    // Generation rather than getting its own untethered color.
    const byId = new Map(steps.map((s) => [s.seq, s]))
    const spine = steps.filter((s) => s.kind === 'node')

    const stageOf = (s: AgentStep): Stage => {
      if (s.kind === 'node') return NODE_STAGE[s.name] ?? 'probe'
      const parent = s.parent_seq != null ? byId.get(s.parent_seq) : undefined
      return parent ? (NODE_STAGE[parent.name] ?? 'probe') : 'probe'
    }

    steps.forEach((s) => {
      const out = s.output ?? {}
      let sub: string | undefined
      if (out.evidence_count !== undefined) sub = `${out.evidence_count} evidence`
      else if (out.hypotheses) sub = `${out.hypotheses.length} hypotheses`
      else if (out.candidate_services) sub = `${out.candidate_services.length} candidates`
      else if (out.verification_result) sub = out.verification_result.passed ? 'passed' : 'failed'

      const label = s.kind === 'node' ? (FRIENDLY_LABEL[s.name] ?? s.name) : s.name

      ns.push({
        id: String(s.seq),
        type: 'step',
        position: { x: 0, y: 0 },
        data: {
          label,
          sub,
          stage: stageOf(s),
          status: s.status,
          title: `${s.name} (${s.kind}) — ${s.status}`,
        },
      })

      if (s.parent_seq != null) {
        es.push({
          id: `e${s.parent_seq}-${s.seq}`,
          source: String(s.parent_seq),
          target: String(s.seq),
          animated: false,
        })
      }
    })

    // Chain consecutive spine nodes so the main path reads top to bottom.
    spine.forEach((s, i) => {
      if (i === 0) return
      es.push({
        id: `spine${spine[i - 1].seq}-${s.seq}`,
        source: String(spine[i - 1].seq),
        target: String(s.seq),
      })
    })

    return { nodes: layout(ns, es), edges: es }
  }, [steps])

  if (steps.length === 0) return <p className="dim pad">No steps recorded yet.</p>

  return (
    <div className="graphwrap">
      <Legend />
      <div className="graph">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
        >
          <Background gap={16} color="#1c1c22" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  )
}
