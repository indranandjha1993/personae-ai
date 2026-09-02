import { beforeEach, describe, expect, it } from 'vitest'

import { BargeInDetector, frameLevel } from './barge-in'

describe('BargeInDetector', () => {
  let detector: BargeInDetector

  beforeEach(() => { detector = new BargeInDetector() })

  const feed = (input: number, playback: number, times: number): boolean => {
    let fired = false
    for (let i = 0; i < times; i += 1) fired = detector.observe(input, playback) || fired
    return fired
  }

  it('ignores silence', () => {
    expect(feed(0, 0, 10)).toBe(false)
  })

  it('ignores room noise below the floor', () => {
    expect(feed(0.01, 0, 10)).toBe(false)
  })

  it('ignores the reply leaking back through the microphone', () => {
    // Input roughly matches what is playing: that is echo, not speech.
    expect(feed(0.2, 0.18, 10)).toBe(false)
  })

  it('fires when someone speaks clearly over the reply', () => {
    expect(feed(0.6, 0.15, 5)).toBe(true)
  })

  it('needs sustained sound, not a single loud frame', () => {
    expect(detector.observe(0.6, 0.05)).toBe(false)
  })

  it('forgets a burst that stops before it qualifies', () => {
    detector.observe(0.6, 0.05)
    detector.observe(0, 0.05)
    expect(detector.observe(0.6, 0.05)).toBe(false)
  })
})

describe('frameLevel', () => {
  it('is zero for silence and for an empty frame', () => {
    expect(frameLevel(new Int16Array(64))).toBe(0)
    expect(frameLevel(new Int16Array(0))).toBe(0)
  })

  it('rises with amplitude', () => {
    const quiet = frameLevel(new Int16Array(64).fill(1000))
    const loud = frameLevel(new Int16Array(64).fill(20000))
    expect(loud).toBeGreaterThan(quiet)
    expect(loud).toBeLessThanOrEqual(1)
  })
})
