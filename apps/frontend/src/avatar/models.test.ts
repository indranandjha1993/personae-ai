import { afterEach, describe, expect, it, vi } from 'vitest'

import { BUILT_IN, findAvailableModels, MODEL_CHOICES } from './models'

afterEach(() => { vi.unstubAllGlobals() })

function stubFetch(responder: (url: string) => { ok: boolean; type?: string }) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const { ok, type = 'application/octet-stream' } = responder(url)
      return Promise.resolve({ ok, headers: { get: () => type } })
    }),
  )
}

describe('findAvailableModels', () => {
  it('returns only the models that are actually present', async () => {
    stubFetch((url) => ({ ok: url.includes('seed-san') }))
    const found = await findAvailableModels()
    expect(found.map((choice) => choice.id)).toEqual(['seed-san'])
  })

  it('rejects a dev server answering 200 with an HTML page', async () => {
    // Vite serves index.html for a missing file, so status alone is not proof.
    stubFetch(() => ({ ok: true, type: 'text/html' }))
    expect(await findAvailableModels()).toEqual([])
  })

  it('treats a network failure as absent rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))))
    expect(await findAvailableModels()).toEqual([])
  })

  it('credits every model, so licensing is visible in the interface', () => {
    for (const choice of [...MODEL_CHOICES, BUILT_IN]) {
      expect(choice.credit).not.toBe('')
    }
  })
})
