import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiContractError, ApiUnavailable, getHealth, getRun, getStatus, startCollect } from './client.ts'

// Реальний приклад відповіді /status (контракт http-api).
const STATUS = {
  last_run: {
    id: 5, started_at: '2026-09-28T11:52:38.183420Z', finished_at: '2026-09-28T11:52:38.552394Z',
    status: 'no_changes', trigger: 'manual', changed_days: [], error_message: null,
  },
  last_update: {
    id: 3, started_at: '2026-09-28T09:00:00Z', finished_at: '2026-09-28T09:00:02Z',
    status: 'success', trigger: 'manual', changed_days: ['2026-09-29'], error_message: null,
  },
  recent_errors: [],
}

function respond(status: number, body?: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('getStatus', () => {
  it('returns the contract shape from /api/status', async () => {
    const fetchMock = respond(200, STATUS)
    await expect(getStatus()).resolves.toEqual(STATUS)
    expect(fetchMock).toHaveBeenCalledWith('/api/status', expect.anything())
  })

  it('sends no credentials — the API has no authentication', async () => {
    const fetchMock = respond(200, STATUS)
    await getStatus()
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
    expect(init.credentials ?? 'same-origin').toBe('same-origin')
  })

  it('401 is an unexpected response now -> ApiContractError', async () => {
    respond(401, { detail: 'authentication required' })
    await expect(getStatus()).rejects.toBeInstanceOf(ApiContractError)
  })

  it.each([502, 504, 500])('%i -> ApiUnavailable', async (code) => {
    respond(code)
    await expect(getStatus()).rejects.toBeInstanceOf(ApiUnavailable)
  })

  it('network failure -> ApiUnavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(getStatus()).rejects.toBeInstanceOf(ApiUnavailable)
  })

  it('200 without recent_errors -> ApiContractError', async () => {
    respond(200, { last_run: null, last_update: null })
    await expect(getStatus()).rejects.toBeInstanceOf(ApiContractError)
  })
})

describe('getHealth', () => {
  it('accepts {"status": "ok"}', async () => {
    respond(200, { status: 'ok' })
    await expect(getHealth()).resolves.toEqual({ status: 'ok' })
  })

  it('rejects an unexpected body', async () => {
    respond(200, { status: 'nope' })
    await expect(getHealth()).rejects.toBeInstanceOf(ApiContractError)
  })
})

describe('collect', () => {
  it('startCollect POSTs /api/collect and parses 202', async () => {
    const f = respond(202, { run_id: 5, status_url: '/runs/5' })
    await expect(startCollect()).resolves.toEqual({ run_id: 5, status_url: '/runs/5' })
    expect(f.mock.calls[0][0]).toBe('/api/collect')
    expect((f.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('startCollect without integer run_id -> ApiContractError', async () => {
    respond(202, { run_id: 'x' })
    await expect(startCollect()).rejects.toBeInstanceOf(ApiContractError)
  })

  it('getRun reads /api/runs/{id}', async () => {
    const run = { ...STATUS.last_run, id: 5, status: null, finished_at: null }
    const f = respond(200, run)
    await expect(getRun(5)).resolves.toEqual(run)
    expect(f.mock.calls[0][0]).toBe('/api/runs/5')
  })
})
