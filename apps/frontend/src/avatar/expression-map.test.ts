import { describe, expect, it } from 'vitest'

import { ACTIVITY_POSE, mouthOpenness, toPose, toVrmEmotion, VISEMES } from './expression-map'

describe('toVrmEmotion', () => {
  it('maps character emotions onto VRM presets', () => {
    expect(toVrmEmotion('amused')).toBe('happy')
    expect(toVrmEmotion('indignant')).toBe('angry')
    expect(toVrmEmotion('solemn')).toBe('sad')
  })

  it('degrades an unknown emotion to neutral rather than throwing', () => {
    expect(toVrmEmotion('exuberant')).toBe('neutral')
    expect(toVrmEmotion('')).toBe('neutral')
  })
})

describe('toPose', () => {
  it('gives distinct poses to distinct gestures', () => {
    expect(toPose('gesture-point')).not.toEqual(toPose('gesture-dismiss'))
  })

  it('rests for idle and for anything unmapped', () => {
    const resting = { armSwing: 0, headTilt: 0, torsoTwist: 0 }
    expect(toPose('idle')).toEqual(resting)
    expect(toPose('gesture-cartwheel')).toEqual(resting)
  })
})

describe('mouthOpenness', () => {
  it('is closed in silence and open when loud', () => {
    expect(mouthOpenness(0)).toBe(0)
    expect(mouthOpenness(1)).toBe(1)
  })

  it('rises monotonically with loudness', () => {
    const points = [0, 0.02, 0.05, 0.1, 0.2].map(mouthOpenness)
    for (let i = 1; i < points.length; i += 1) {
      expect(points[i] ?? 0).toBeGreaterThanOrEqual(points[i - 1] ?? 0)
    }
  })

  it('never exceeds the valid weight range', () => {
    for (const rms of [0, 0.5, 1, 5]) {
      expect(mouthOpenness(rms)).toBeGreaterThanOrEqual(0)
      expect(mouthOpenness(rms)).toBeLessThanOrEqual(1)
    }
  })

  it('exposes the VRM viseme names', () => {
    expect(VISEMES).toContain('aa')
    expect(VISEMES).toHaveLength(5)
  })
})

describe('ACTIVITY_POSE', () => {
  it('makes thinking visibly different from listening', () => {
    // A character that looks identical while waiting and while working reads as
    // frozen rather than considering.
    expect(ACTIVITY_POSE.thinking).not.toEqual(ACTIVITY_POSE.listening)
    expect(Math.abs(ACTIVITY_POSE.thinking.headYaw)).toBeGreaterThan(
      Math.abs(ACTIVITY_POSE.listening.headYaw),
    )
  })

  it('holds stiller while listening than while idle', () => {
    expect(ACTIVITY_POSE.listening.sway).toBeLessThan(ACTIVITY_POSE.idle.sway)
  })

  it('leans in to listen and away to think', () => {
    expect(ACTIVITY_POSE.listening.lean).toBeGreaterThan(0)
    expect(ACTIVITY_POSE.thinking.lean).toBeLessThan(ACTIVITY_POSE.listening.lean)
  })

  it('covers every activity the conversation can report', () => {
    for (const activity of ['idle', 'listening', 'thinking', 'speaking', 'error'] as const) {
      expect(ACTIVITY_POSE[activity]).toBeDefined()
    }
  })
})
