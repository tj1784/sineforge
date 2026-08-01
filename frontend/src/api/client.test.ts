import { afterEach, describe, expect, it, vi } from 'vitest'

import { BackendUnavailableError, api } from './client'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('backend transport recovery', () => {
  it('retries an idempotent GET after a transient network failure', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('connection refused'))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const request = api.health()
    await vi.runAllTimersAsync()

    await expect(request).resolves.toMatchObject({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('never automatically repeats a mutating request', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('connection refused'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.startEngine()).rejects.toBeInstanceOf(BackendUnavailableError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('returns a typed reconnecting error after GET retries are exhausted', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('connection refused'))
    vi.stubGlobal('fetch', fetchMock)

    const request = api.health()
    const expectation = expect(request).rejects.toBeInstanceOf(BackendUnavailableError)
    await vi.runAllTimersAsync()

    await expectation
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
