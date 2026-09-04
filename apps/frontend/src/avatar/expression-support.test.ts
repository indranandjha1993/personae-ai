import { describe, expect, it } from 'vitest'

import { BROW_EXPRESSIONS, browChannel } from './expression-support'

describe('browChannel', () => {
  it('uses the authored brows when the model has them', () => {
    expect(browChannel(() => true)).toEqual({ mode: 'custom', missing: [] })
  })

  it('falls back to the surprised preset and names what is missing', () => {
    // Regression: the bundled model has no custom expressions, so the brow
    // weights were being set on nothing and every accent went unseen.
    const channel = browChannel((name) => name === 'eye_brow_up_L')
    expect(channel.mode).toBe('surprised')
    expect(channel.missing).toEqual(['eye_brow_up_R'])
  })

  it('checks every brow expression the tracker drives', () => {
    const asked: string[] = []
    browChannel((name) => { asked.push(name); return false })
    expect(asked).toEqual([...BROW_EXPRESSIONS])
  })
})
