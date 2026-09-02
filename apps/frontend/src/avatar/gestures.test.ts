/**
 * The gesture vocabulary.
 *
 * These check the shape of the poses rather than exact angles: the numbers are
 * tuned by eye, but a pose that bends an elbow backwards or moves both arms
 * identically is wrong regardless of taste.
 */

import { describe, expect, it } from 'vitest'

import { blendPoses, GESTURE_NAMES, REST, toBodyPose } from './gestures'

describe('the gesture vocabulary', () => {
  it('falls back to rest for a gesture it does not know', () => {
    expect(toBodyPose('gesture-cartwheel')).toEqual(REST)
  })

  it.each(GESTURE_NAMES)('%s never bends an elbow backwards', (name) => {
    // Elbows fold one way. A negative value here would snap the arm.
    const pose = toBodyPose(name)
    expect(pose.left.elbow).toBeGreaterThanOrEqual(0)
    expect(pose.right.elbow).toBeGreaterThanOrEqual(0)
  })

  it.each(GESTURE_NAMES)('%s keeps finger curl within a hand', (name) => {
    const pose = toBodyPose(name)
    for (const arm of [pose.left, pose.right]) {
      expect(arm.curl).toBeGreaterThanOrEqual(0)
      expect(arm.curl).toBeLessThanOrEqual(1)
    }
  })

  it('rests with a bend in the arm rather than straight', () => {
    // A perfectly straight arm with splayed fingers is the strongest
    // "mannequin" cue there is.
    expect(REST.left.elbow).toBeGreaterThan(0)
    expect(REST.left.curl).toBeGreaterThan(0)
  })

  it('leads with one hand on gestures that single something out', () => {
    // Both arms doing the same thing reads as a puppet; people point with one.
    const point = toBodyPose('gesture-point')
    expect(point.right.upperForward).toBeGreaterThan(point.left.upperForward + 0.3)
  })
})

describe('easing between gestures', () => {
  it('is the start pose at zero and the end pose at one', () => {
    const from = toBodyPose('idle')
    const to = toBodyPose('gesture-declaim')
    // Interpolating to the endpoint is not bit-identical to it, so compare
    // by closeness rather than equality.
    expect(blendPoses(from, to, 0).left.elbow).toBeCloseTo(from.left.elbow)
    expect(blendPoses(from, to, 1).left.elbow).toBeCloseTo(to.left.elbow)
    expect(blendPoses(from, to, 1).right.curl).toBeCloseTo(to.right.curl)
  })

  it('passes through the middle rather than snapping', () => {
    const from = toBodyPose('idle')
    const to = toBodyPose('gesture-declaim')
    const half = blendPoses(from, to, 0.5)
    expect(half.left.upperForward).toBeGreaterThan(from.left.upperForward)
    expect(half.left.upperForward).toBeLessThan(to.left.upperForward)
  })
})

describe('everyday motions', () => {
  it.each(['gesture-yes', 'gesture-no', 'gesture-wave'] as const)(
    '%s carries a movement, not only a pose',
    (name) => {
      // A nod or a wave is an oscillation; a held position would read as a
      // freeze-frame of one.
      expect(toBodyPose(name).motion).toBeDefined()
    },
  )

  it('namaste is symmetric, unlike the speaking gestures', () => {
    // Palms meet in the middle; this is the one gesture where matched arms
    // are the point rather than a puppet tell.
    const pose = toBodyPose('gesture-namaste')
    expect(pose.left.upperForward).toBe(pose.right.upperForward)
    expect(pose.left.elbow).toBe(pose.right.elbow)
    expect(pose.headTilt).toBeGreaterThan(0)
  })
})
