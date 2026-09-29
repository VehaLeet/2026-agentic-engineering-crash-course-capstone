import type { Candidate, NotificationsSettings, Recipient, Run, Schedule, SystemStatus, TestResult } from './types.ts'

const BASE = '/api'

/** Мережева помилка або 5xx (зокрема 502/504 від проксі, коли backend не запущено). */
export class ApiUnavailable extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiUnavailable'
  }
}

/** 422: запит відхилено валідацією API; detail — повідомлення API для користувача. */
export class ApiValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiValidationError'
  }
}

/** 404 чи 409 з ендпойнтів налаштувань: detail — повідомлення API. Інші 4xx лишаються ApiContractError. */
export class ApiRequestError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

/** 200, але тіло не відповідає контракту — краще явна помилка, ніж тихі undefined. */
export class ApiContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiContractError'
  }
}

interface RequestOptions extends RequestInit {
  json?: unknown
}

async function detailOf(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null)
  return typeof body?.detail === 'string' ? body.detail : fallback
}

export async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
  const { json, ...init } = options
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (json !== undefined) headers['Content-Type'] = 'application/json'
  let response: Response
  try {
    // Автентифікації немає (ранній MVP): облікові дані не надсилаються.
    response = await fetch(`${BASE}${path}`, {
      ...init,
      ...(json !== undefined ? { body: JSON.stringify(json) } : {}),
      headers: { ...headers, ...init.headers },
    })
  } catch (e) {
    throw new ApiUnavailable(`мережева помилка: ${(e as Error).message}`)
  }
  if (response.status === 502) {
    // 502 від backend може нести пояснення (напр., збій Telegram); від проксі Vite тіла з detail немає.
    throw new ApiUnavailable(await detailOf(response, 'HTTP 502'))
  }
  if (response.status >= 500) throw new ApiUnavailable(`HTTP ${response.status}`)
  if (response.status === 422) throw new ApiValidationError(await detailOf(response, 'некоректний запит'))
  if (response.status === 404 || response.status === 409) {
    throw new ApiRequestError(response.status, await detailOf(response, `HTTP ${response.status}`))
  }
  if (!response.ok) throw new ApiContractError(`неочікуваний HTTP ${response.status}`)
  if (response.status === 204) return null
  try {
    return await response.json()
  } catch {
    throw new ApiContractError('відповідь не є JSON')
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export async function getHealth(): Promise<{ status: 'ok' }> {
  const body = await request('/health')
  if (!isObject(body) || body.status !== 'ok') throw new ApiContractError('неочікувана відповідь /health')
  return { status: 'ok' }
}

export async function getStatus(): Promise<SystemStatus> {
  const body = await request('/status')
  if (!isObject(body) || !('last_run' in body) || !('last_update' in body) || !Array.isArray(body.recent_errors)) {
    throw new ApiContractError('неочікувана відповідь /status')
  }
  return body as unknown as SystemStatus
}

/** POST /collect: запуск збору у фоні, відповідь 202 з ідентифікатором запуску. */
export async function startCollect(): Promise<{ run_id: number; status_url: string }> {
  const body = await request('/collect', { method: 'POST' })
  if (!isObject(body) || !Number.isInteger(body.run_id)) throw new ApiContractError('неочікувана відповідь /collect')
  return body as unknown as { run_id: number; status_url: string }
}

/** GET /runs/{id}: status === null, поки запуск триває. */
export async function getRun(id: number): Promise<Run> {
  const body = await request(`/runs/${id}`)
  if (!isObject(body) || body.id !== id || !('status' in body)) throw new ApiContractError('неочікувана відповідь /runs')
  return body as unknown as Run
}

// --- Налаштування (контракти collection-schedule і telegram-settings) ---

function isSchedule(b: unknown): b is Schedule {
  return isObject(b) && typeof b.enabled === 'boolean' && Number.isInteger(b.interval_minutes) &&
    (b.next_run_at === null || typeof b.next_run_at === 'string')
}

function isRecipient(b: unknown): b is Recipient {
  return isObject(b) && typeof b.chat_id === 'string' && typeof b.enabled === 'boolean'
}

function checked<T>(body: unknown, ok: (b: unknown) => b is T, what: string): T {
  if (!ok(body)) throw new ApiContractError(`неочікувана відповідь ${what}`)
  return body
}

const recipientPath = (chatId: string) => `/settings/telegram/recipients/${encodeURIComponent(chatId)}`

export async function getSchedule(): Promise<Schedule> {
  return checked(await request('/settings/schedule'), isSchedule, '/settings/schedule')
}

export async function putSchedule(value: { enabled: boolean; interval_minutes: number }): Promise<Schedule> {
  return checked(await request('/settings/schedule', { method: 'PUT', json: value }), isSchedule, '/settings/schedule')
}

function isNotifications(b: unknown): b is NotificationsSettings {
  return isObject(b) && typeof b.enabled === 'boolean' && typeof b.token_configured === 'boolean'
}

export async function getNotifications(): Promise<NotificationsSettings> {
  return checked(await request('/settings/notifications'), isNotifications, '/settings/notifications')
}

export async function putNotifications(enabled: boolean): Promise<NotificationsSettings> {
  const body = await request('/settings/notifications', { method: 'PUT', json: { enabled } })
  return checked(body, isNotifications, '/settings/notifications')
}

export async function listRecipients(): Promise<Recipient[]> {
  const body = await request('/settings/telegram/recipients')
  const all = (b: unknown): b is Recipient[] => Array.isArray(b) && b.every(isRecipient)
  return checked(body, all, '/settings/telegram/recipients')
}

export async function addRecipient(chatId: string): Promise<Recipient> {
  const body = await request('/settings/telegram/recipients', { method: 'POST', json: { chat_id: chatId } })
  return checked(body, isRecipient, '/settings/telegram/recipients')
}

export async function setRecipientEnabled(chatId: string, enabled: boolean): Promise<Recipient> {
  return checked(await request(recipientPath(chatId), { method: 'PATCH', json: { enabled } }), isRecipient, 'recipient')
}

export async function deleteRecipient(chatId: string): Promise<void> {
  await request(recipientPath(chatId), { method: 'DELETE' })
}

export async function testRecipient(chatId: string): Promise<TestResult> {
  const body = await request(`${recipientPath(chatId)}/test`, { method: 'POST' })
  const ok = (b: unknown): b is TestResult =>
    isObject(b) && typeof b.ok === 'boolean' && (b.error === undefined || b.error === null || typeof b.error === 'string')
  return checked(body, ok, 'recipient test')
}

function isCandidate(b: unknown): b is Candidate {
  return isObject(b) && typeof b.chat_id === 'string' && typeof b.type === 'string' && typeof b.title === 'string' &&
    (b.username === null || typeof b.username === 'string') && typeof b.last_seen_at === 'string' &&
    typeof b.added === 'boolean'
}

/** Чати, що нещодавно писали боту (getUpdates на боці сервера). Запит іде в Telegram — лише за дією. */
export async function listCandidates(): Promise<Candidate[]> {
  const body = await request('/settings/telegram/candidates')
  const all = (b: unknown): b is Candidate[] => Array.isArray(b) && b.every(isCandidate)
  return checked(body, all, '/settings/telegram/candidates')
}
