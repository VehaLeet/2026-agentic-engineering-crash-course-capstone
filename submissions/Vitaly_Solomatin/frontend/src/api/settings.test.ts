import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  addRecipient, ApiContractError, ApiRequestError, ApiUnavailable, ApiValidationError, deleteRecipient, getSchedule,
  listCandidates, listRecipients, putNotifications, putSchedule, setRecipientEnabled, testRecipient,
} from './client.ts'

function respond(status: number, body?: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const call = (m: ReturnType<typeof respond>) => {
  const [url, init] = m.mock.calls[0] as [string, RequestInit]
  return { url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body as string) : undefined,
    contentType: new Headers(init.headers).get('Content-Type') }
}

afterEach(() => vi.unstubAllGlobals())

describe('request errors', () => {
  it('404 and 409 carry the server detail', async () => {
    respond(404, { detail: 'recipient not found' })
    await expect(setRecipientEnabled('555', true)).rejects.toEqual(new ApiRequestError(404, 'recipient not found'))
    respond(409, { detail: 'TELEGRAM_BOT_TOKEN не задано' })
    const err = await testRecipient('1').catch((e) => e)
    expect(err).toBeInstanceOf(ApiRequestError)
    expect([err.status, err.message]).toEqual([409, 'TELEGRAM_BOT_TOKEN не задано'])
  })

  it('422 stays a validation error', async () => {
    respond(422, { detail: 'некоректний chat_id' })
    await expect(addRecipient('hello world')).rejects.toBeInstanceOf(ApiValidationError)
  })

  it('204 has no body', async () => {
    const m = respond(204)
    await expect(deleteRecipient('123')).resolves.toBeUndefined()
    expect(call(m)).toMatchObject({ url: '/api/settings/telegram/recipients/123', method: 'DELETE' })
  })
})

describe('settings calls', () => {
  it('putSchedule sends JSON and returns the schedule', async () => {
    const schedule = { enabled: true, interval_minutes: 15, next_run_at: '2026-09-29T09:00:00Z' }
    const m = respond(200, schedule)
    await expect(putSchedule({ enabled: true, interval_minutes: 15 })).resolves.toEqual(schedule)
    expect(call(m)).toEqual({ url: '/api/settings/schedule', method: 'PUT', body: { enabled: true, interval_minutes: 15 },
      contentType: 'application/json' })
  })

  it('putNotifications and recipients use the documented paths', async () => {
    let m = respond(200, { enabled: false, token_configured: true })
    await putNotifications(false)
    expect(call(m)).toMatchObject({ url: '/api/settings/notifications', method: 'PUT', body: { enabled: false } })
    m = respond(201, { chat_id: '123', enabled: true })
    await addRecipient('123')
    expect(call(m)).toMatchObject({ url: '/api/settings/telegram/recipients', method: 'POST', body: { chat_id: '123' } })
    m = respond(200, { chat_id: '@oree_dam', enabled: false })
    await setRecipientEnabled('@oree_dam', false)
    expect(call(m)).toMatchObject({ url: '/api/settings/telegram/recipients/%40oree_dam', method: 'PATCH', body: { enabled: false } })
    m = respond(200, { ok: false, error: 'HTTP 403' })
    await expect(testRecipient('-100')).resolves.toEqual({ ok: false, error: 'HTTP 403' })
    expect(call(m)).toMatchObject({ url: '/api/settings/telegram/recipients/-100/test', method: 'POST' })
  })

  it('rejects responses of the wrong shape', async () => {
    respond(200, { enabled: 'yes' })
    await expect(getSchedule()).rejects.toBeInstanceOf(ApiContractError)
    respond(200, [{ chat_id: 1 }])
    await expect(listRecipients()).rejects.toBeInstanceOf(ApiContractError)
  })
})

describe('candidates', () => {
  const CANDIDATE = { chat_id: '987654321', type: 'private', title: 'Олена', username: 'olena',
    last_seen_at: '2026-09-29T08:51:30Z', added: false }

  it('listCandidates reads the documented path', async () => {
    const m = respond(200, [CANDIDATE])
    await expect(listCandidates()).resolves.toEqual([CANDIDATE])
    expect(call(m)).toMatchObject({ url: '/api/settings/telegram/candidates', method: 'GET' })
  })

  it('rejects candidates of the wrong shape', async () => {
    respond(200, [{ ...CANDIDATE, added: 'no' }])
    await expect(listCandidates()).rejects.toBeInstanceOf(ApiContractError)
  })

  it('502 from the backend carries the Telegram detail; bare 502 stays generic', async () => {
    respond(502, { detail: "HTTP 409: Conflict: can't use getUpdates method while webhook is active" })
    const err = await listCandidates().catch((e) => e)
    expect(err).toBeInstanceOf(ApiUnavailable)
    expect(err.message).toContain('webhook is active')
    respond(502)
    await expect(listCandidates()).rejects.toEqual(new ApiUnavailable('HTTP 502'))
  })
})
