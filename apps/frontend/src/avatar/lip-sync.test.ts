import { describe, expect, it } from 'vitest'

import type { AudioFeatures } from '../audio/playback'
import { LipSync } from './lip-sync'

const speech = (over: Partial<AudioFeatures> = {}): AudioFeatures => ({
  rms: 0.09, frontness: 0.5, openness: 0.5, sibilance: 0.05, voiced: 1, ...over,
})

const silence: AudioFeatures = {
  rms: 0, frontness: 0.5, openness: 0, sibilance: 0, voiced: 0,
}

/** Weights are reused between frames, so snapshots must be copied. */
const settle = (lip: LipSync, features: AudioFeatures, seconds = 0.6) => {
  let out = lip.update(features, 1 / 60)
  for (let t = 0; t < seconds; t += 1 / 60) out = lip.update(features, 1 / 60)
  return { ...out }
}

describe('LipSync', () => {
  it('opens the jaw when she is loud and closes it when she stops', () => {
    const lip = new LipSync()
    const loud = settle(lip, speech({ rms: 0.2, openness: 0.9 }))
    const quiet = settle(lip, silence, 1.5)
    expect(loud.jaw).toBeGreaterThan(quiet.jaw)
  })

  it('rests with the lips parted rather than sealed shut', () => {
    const lip = new LipSync()
    expect(settle(lip, silence, 2).jaw).toBeGreaterThan(0)
  })

  it('spreads the mouth for front vowels and rounds it for back ones', () => {
    const front = settle(new LipSync(), speech({ frontness: 0.95 }))
    const back = settle(new LipSync(), speech({ frontness: 0.05 }))
    expect(front.ee + front.ih).toBeGreaterThan(back.ee + back.ih)
    expect(back.oh + back.ou).toBeGreaterThan(front.oh + front.ou)
    expect(front.wide).toBeGreaterThan(back.wide)
  })

  it('keeps the jaw shut on hiss instead of dropping it', () => {
    // An "s" carries little energy; a loudness-only mouth gapes on it.
    const lip = new LipSync()
    const hiss = settle(lip, speech({ rms: 0.02, voiced: 0.1, sibilance: 0.6 }))
    expect(hiss.jaw).toBeLessThan(0.2)
    expect(hiss.wide).toBeGreaterThan(0.2)
  })

  it('never stacks the vowel morphs past what the mesh can take', () => {
    const lip = new LipSync()
    for (const frontness of [0, 0.25, 0.5, 0.75, 1]) {
      for (const openness of [0, 0.5, 1]) {
        const w = settle(lip, speech({ frontness, openness, rms: 0.3 }), 0.3)
        expect(w.aa + w.ih + w.ou + w.ee + w.oh).toBeLessThanOrEqual(0.9)
      }
    }
  })

  it('holds the shape through a brief gap between words', () => {
    const lip = new LipSync()
    const speaking = settle(lip, speech({ rms: 0.2, openness: 0.9 }))
    const gap = lip.update(silence, 0.05)
    expect(gap.jaw).toBeGreaterThan(speaking.jaw * 0.6)
  })

  it('reports how long she has been quiet', () => {
    const lip = new LipSync()
    settle(lip, speech())
    expect(lip.pauseSeconds).toBe(0)
    settle(lip, silence, 0.5)
    expect(lip.pauseSeconds).toBeGreaterThan(0.4)
  })
})
