import { describe, expect, it } from 'vitest'

import { EmphasisTracker } from './emphasis'

const run = (tracker: EmphasisTracker, rms: number, seconds: number, speaking = true) => {
  const frames = []
  for (let t = 0; t < seconds; t += 1 / 60) frames.push(tracker.update(rms, 1 / 60, speaking))
  return frames
}

describe('EmphasisTracker', () => {
  it('accents a rise in loudness, not a steady level', () => {
    const tracker = new EmphasisTracker()
    const steady = run(tracker, 0.1, 2).filter((f) => f.accent > 0).length
    const surge = run(tracker, 0.35, 0.5).filter((f) => f.accent > 0).length
    expect(surge).toBeGreaterThan(0)
    expect(steady).toBeLessThanOrEqual(1)
  })

  it('does not fire constantly while she talks', () => {
    const tracker = new EmphasisTracker()
    let accents = 0
    for (let t = 0; t < 10; t += 1 / 60) {
      const rms = 0.1 + (Math.sin(t * 6) > 0.7 ? 0.25 : 0)
      if (tracker.update(rms, 1 / 60, true).accent > 0) accents += 1
    }
    // Roughly the rate of stressed syllables, not one per frame.
    expect(accents).toBeLessThan(35)
  })

  it('stays still when she is not speaking', () => {
    const tracker = new EmphasisTracker()
    expect(run(tracker, 0.3, 2, false).every((f) => f.accent === 0)).toBe(true)
  })

  it('moves the brows unevenly, which is what reads as alive', () => {
    const tracker = new EmphasisTracker()
    let uneven = false
    for (let t = 0; t < 12; t += 1 / 60) {
      const rms = 0.1 + (Math.sin(t * 5) > 0.6 ? 0.3 : 0)
      const frame = tracker.update(rms, 1 / 60, true)
      if (Math.abs(frame.browLeft - frame.browRight) > 0.02) uneven = true
    }
    expect(uneven).toBe(true)
  })

  it('keeps every weight inside its valid range', () => {
    const tracker = new EmphasisTracker()
    for (let t = 0; t < 12; t += 1 / 60) {
      const frame = tracker.update(0.1 + Math.random() * 0.3, 1 / 60, true)
      expect(frame.browLeft).toBeGreaterThanOrEqual(0)
      expect(frame.browLeft).toBeLessThanOrEqual(1)
      expect(frame.browRight).toBeLessThanOrEqual(1)
      expect(Math.abs(frame.nod)).toBeLessThan(0.1)
    }
  })
})
