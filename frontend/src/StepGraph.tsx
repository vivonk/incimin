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

const W = 190
const H = 48

function StepNode({ data }: NodeProps) {
  const d = data as unknown as { label: string; sub?: string; kind: string; status: string }
  return (
    <div className={`gnode k-${d.kind} st-${d.status}`}>
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

export default function StepGraph({ steps }: { steps: AgentStep[] }) {
  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = []
    const es: Edge[] = []

    // `node` rows form the spine in execution order; anything with a parent_seq
    // (probe results, tool calls) hangs off the node that produced it.
    const spine = steps.filter((s) => s.kind === 'node')

    steps.forEach((s) => {
      const out = s.output ?? {}
      let sub: string | undefined
      if (out.evidence_count !== undefined) sub = `${out.evidence_count} evidence`
      else if (out.hypotheses) sub = `${out.hypotheses.length} hypotheses`
      else if (out.candidate_services) sub = `${out.candidate_services.length} candidates`
      else if (out.verification_result) sub = out.verification_result.passed ? 'passed' : 'failed'

      ns.push({
        id: String(s.seq),
        type: 'step',
        position: { x: 0, y: 0 },
        data: { label: s.name, sub, kind: s.kind, status: s.status },
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
        <Background gap={16} color="#252b36" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
