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

// Налаштування (openspec/specs/collection-schedule, openspec/specs/telegram-settings).

export const INTERVAL_MIN = 5 // хвилин; ті самі межі перевіряє бекенд
export const INTERVAL_MAX = 1440

export interface Schedule {
  enabled: boolean
  interval_minutes: number
  next_run_at: string | null // ISO 8601; null — розклад вимкнено
}

export interface NotificationsSettings {
  enabled: boolean
  token_configured: boolean
}

export interface Recipient {
  chat_id: string
  enabled: boolean
}

export interface TestResult {
  ok: boolean
  error?: string | null
}

export interface Candidate {
  chat_id: string
  type: string // private | group | supergroup | channel
  title: string
  username: string | null
  last_seen_at: string // ISO 8601
  added: boolean
}
