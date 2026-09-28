import type { Run, SystemStatus } from './types.ts'

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

/** 200, але тіло не відповідає контракту — краще явна помилка, ніж тихі undefined. */
export class ApiContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiContractError'
  }
}

export async function request(path: string, init: RequestInit = {}): Promise<unknown> {
  let response: Response
  try {
    // Автентифікації немає (ранній MVP): облікові дані не надсилаються.
    response = await fetch(`${BASE}${path}`, { ...init, headers: { Accept: 'application/json', ...init.headers } })
  } catch (e) {
    throw new ApiUnavailable(`мережева помилка: ${(e as Error).message}`)
  }
  if (response.status >= 500) throw new ApiUnavailable(`HTTP ${response.status}`)
  if (response.status === 422) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : 'некоректний запит'
    throw new ApiValidationError(detail)
  }
  if (!response.ok) throw new ApiContractError(`неочікуваний HTTP ${response.status}`)
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
