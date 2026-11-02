export type ProjectState = {
  status: 'ok' | 'needs_confirmation' | 'unknown' | 'model_error' | 'never'
  reason: string
  current_phase: string | null
  current_phase_ordinal: number | null
  accepted_phase?: string | null
  testing: boolean
  newest_record_date: string | null
  scan_error: string | null
  scanned_at: string | null
  last_success_at?: string | null
  files_scanned: number
  basis?: string
  model_status?: 'disabled' | 'ok' | 'invalid' | 'failed' | 'skipped' | string
}

export type Project = {
  id: string
  name: string
  folder_path: string
  planned_start: string
  planned_end: string
  color: string
  archived: boolean
  state: ProjectState
}

export type ProjectInput = {
  name: string
  folder_path: string
  planned_start: string
  planned_end: string
}

export type PhaseRow = {
  id: number
  ordinal: number
  name: string
  status: string
  start_date: string | null
  end_date: string | null
  testing: boolean
  source_path: string
  source_heading: string
}

export type EvidenceRow = {
  id: number
  kind: 'progress' | 'phase_status' | 'schedule' | 'summary' | string
  source_path: string
  heading: string
  record_date: string | null
  claim: string
  excerpt: string
  is_newest: boolean
}

export type PendingRow = {
  id: number
  kind: 'schedule_change' | 'ambiguous_state' | 'model_issue' | string
  field: string
  previous_value: string
  candidate_value: string
  source_path: string
  evidence: string
  status: string
  created_at: string
}

export type ModelCitation = {
  evidence_id: string
  quote: string
  supports: string
  source: string
}

export type ScanChange = {
  project_id: string
  project_name: string
  kind: 'phase' | 'record' | 'status' | string
  previous: string | null
  current: string | null
}

export type ScanRun = {
  id: string
  started_at: string
  finished_at: string | null
  result: 'ok' | 'partial' | 'failed'
  projects_total: number
  projects_ok: number
  projects_needing_confirmation: number
  projects_unknown: number
  projects_failed: number
  projects_model_error?: number
  schedule_proposals: number
  model_ok?: number
  model_failed?: number
  model_enabled?: boolean
  changes: ScanChange[]
  message: string
}

export type StateRow = {
  project_id: string
  status: string
  reason: string
  summary: string
  summary_source: string
  accepted_phase: string | null
  accepted_phase_ordinal: number | null
  accepted_phase_start: string | null
  accepted_phase_end: string | null
  candidate_phase: string | null
  candidate_phase_ordinal: number | null
  candidate_phase_start: string | null
  candidate_phase_end: string | null
  current_basis: string
  candidate_testing: boolean
  newest_record_date: string | null
  newest_record_claim: string | null
  newest_record_source: string | null
  files_scanned: number
  evidence_count: number
  scan_error: string | null
  notes: string[]
  scanned_at: string | null
  last_success_at: string | null
  model_status: 'disabled' | 'ok' | 'invalid' | 'failed' | 'skipped' | string
  model_provider: string | null
  model_name: string | null
  model_confidence: string | null
  model_summary: string | null
  model_citations: ModelCitation[]
  model_error: string | null
  model_checked_at: string | null
}

export type ProjectDetailData = {
  project: Project
  state: StateRow | null
  phases: PhaseRow[]
  evidence: EvidenceRow[]
  pending: PendingRow[]
  scan: ScanRun | null
}

export type ProviderOption = {
  id: string
  label: string
  default_base_url: string
}

export type ProviderSettings = {
  enabled: boolean
  provider: string
  base_url: string
  effective_base_url: string
  endpoint_host: string
  model: string
  json_mode: boolean
  api_key_set: boolean
  key_hint: string
  key_storage: 'file' | 'keyring' | string
  last_test_at: string | null
  last_test_ok: boolean | null
  last_test_message: string
  ready: boolean
  providers: ProviderOption[]
}

export type ProviderInput = {
  enabled?: boolean
  provider?: string
  base_url?: string
  model?: string
  json_mode?: boolean
  api_key?: string
}

export type ProviderTest = {
  ok: boolean
  message: string
  latency_ms: number
  provider: string
  model: string
  endpoint_host: string
}
