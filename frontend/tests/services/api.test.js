// Smoke test #2 — fetchWithAuth in services/api.js.
//
// `fetchWithAuth` is the central HTTP helper every API call routes through.
// If its error-handling shape drifts, every consumer breaks silently. These
// tests pin the four contract paths:
//
//   1. happy path: 2xx → returns parsed JSON
//   2. 204: returns null (no body parse)
//   3. non-2xx: throws Error with detail message from response body
//   4. network failure: throws original fetch error
//
// We mock the global `fetch` directly — no need to spin up a server, no
// need to import from a wrapper. ``getToken`` is just a function we hand in.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchWithAuth } from '../../src/services/api.js'

describe('fetchWithAuth', () => {
  let originalFetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on 2xx', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ cameras: [{ id: 'cam_1' }] }),
    })

    const out = await fetchWithAuth('/api/cameras', async () => 'tok_x')

    expect(out).toEqual({ cameras: [{ id: 'cam_1' }] })
    // Authorization header carried the token from getToken().
    const callArgs = globalThis.fetch.mock.calls[0][1]
    expect(callArgs.headers.Authorization).toBe('Bearer tok_x')
  })

  it('returns null on 204 No Content', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('should not be called for 204')
      },
    })

    const out = await fetchWithAuth('/api/widget', async () => 'tok_x')

    expect(out).toBeNull()
  })

  it('throws Error with detail message on non-2xx', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 402,
      json: async () => ({ detail: 'plan_limit_hit: camera over Free-tier cap' }),
    })

    await expect(
      fetchWithAuth('/api/cameras/cam_1/push-segment', async () => 'tok_x'),
    ).rejects.toThrow(/plan_limit_hit/)
  })

  it('throws fetch error when network fails', async () => {
    const networkErr = new TypeError('Failed to fetch')
    globalThis.fetch = vi.fn().mockRejectedValue(networkErr)

    await expect(
      fetchWithAuth('/api/cameras', async () => 'tok_x'),
    ).rejects.toBe(networkErr) // exact same Error instance bubbles up
  })

  it('omits Authorization header when getToken returns null', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    })

    await fetchWithAuth('/api/health', async () => null)

    const headers = globalThis.fetch.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })
})
