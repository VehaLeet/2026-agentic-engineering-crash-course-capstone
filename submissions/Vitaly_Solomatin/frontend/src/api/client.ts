import type { SystemStatus } from './types.ts'

const BASE = '/api'

/** Мережева помилка або 5xx (зокрема 502/504 від проксі, коли backend не запущено). */
export class ApiUnavailable extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiUnavailable'
  }
}

/** 200, але тіло не відповідає контракту — краще явна помилка, ніж тихі undefined. */
export class ApiContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiContractError'
  }
}

async function request(path: string): Promise<unknown> {
  let response: Response
  try {
    // Автентифікації немає (ранній MVP): облікові дані не надсилаються.
    response = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } })
  } catch (e) {
    throw new ApiUnavailable(`мережева помилка: ${(e as Error).message}`)
  }
  if (response.status >= 500) throw new ApiUnavailable(`HTTP ${response.status}`)
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
