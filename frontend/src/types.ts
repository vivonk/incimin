// Mirrors the row shapes returned by src/api/main.py. Kept deliberately close to
// the database columns rather than reshaped, so a field added in schema.sql shows
// up here as a compile error rather than silently going missing.

export type IncidentStatus =
  | 'open'
  | 'agent_running'
  | 'awaiting_approval'
  | 'executing_remediation'
  | 'done'
  | 'needs_human'
  | 'orphaned'
  | 'failed'

export interface Incident {
  id: string
  dedupe_key: string
  fingerprint: string | null
  alertname: string
  service: string
  severity: string | null
  message: string
  status: IncidentStatus
  current_step: string | null
  fired_at: string
  created_at: string
  updated_at: string
  root_cause_service: string | null
  confidence: string | null
  final_answer: string | null
  error: string | null
  labels: Record<string, unknown>
  annotations: Record<string, unknown>
  raw: Record<string, unknown>
}

// Shapes the kernel writes into agent_steps.output via runner._summarize().
// Optional throughout: which keys a step carries depends on which node produced it.

export interface HypothesisView {
  id: string
  kind: string
  service: string
  posterior: number
  status: 'open' | 'refuted' | 'confirmed'
}

export interface VerificationView {
  passed: boolean
  failed_checks: string[]
  detail: string
}

export interface BudgetView {
  max_rounds: number
  rounds_used: number
  exit_reason: string
}

export interface StepOutput {
  hypotheses?: HypothesisView[]
  verification_result?: VerificationView
  budget?: BudgetView
  candidate_services?: string[]
  evidence_count?: number
  summary?: string
  round_index?: number
  synthesis?: {
    root_cause_service: string | null
    confidence: string | null
    evidence_refs: string[]
  }
}

export interface AgentStep {
  id: number
  incident_id: string
  seq: number
  parent_seq: number | null
  kind: 'node' | 'tool_call' | 'tool_result' | 'gate'
  name: string
  status: string
  input: Record<string, unknown> | null
  output: StepOutput | null
  started_at: string
  ended_at: string | null
}
