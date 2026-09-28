// Типи за контрактом http-api (openspec/specs/http-api). OpenAPI вимкнено, тож описані вручну.

export type RunStatus = 'success' | 'no_changes' | 'no_data' | 'error' | 'skipped_locked'

export interface Run {
  id: number
  started_at: string // ISO 8601, UTC
  finished_at: string | null
  status: RunStatus | null // null — запуск ще триває
  trigger: 'manual' | 'scheduled'
  changed_days: string[] // YYYY-MM-DD
  error_message: string | null
}

export interface SystemStatus {
  last_run: Run | null
  last_update: Run | null // останній success
  recent_errors: Run[]
}
