import { describe, expect, it } from 'vitest'

import { ARM_BONES, armTracksOnly, parseManifest } from './motions'

describe('parseManifest', () => {
  it('keeps gesture names mapped to .vrma files', () => {
    expect(parseManifest({ 'gesture-wave': 'wave.vrma', idle: 'breathe.VRMA' })).toEqual({
      'gesture-wave': 'wave.vrma',
      idle: 'breathe.VRMA',
    })
  })

  it('drops anything that is not a gesture name or not a clip file', () => {
    // A manifest is fetched from the network; it is narrowed, not trusted.
    expect(
      parseManifest({
        'gesture-wave': '../../etc/passwd',
        'gesture-point': 42,
        cartwheel: 'flip.vrma',
        'gesture-nod': 'nod.vrma',
      }),
    ).toEqual({ 'gesture-nod': 'nod.vrma' })
  })

  it('treats a manifest of the wrong shape as empty', () => {
    expect(parseManifest(null)).toEqual({})
    expect(parseManifest(['gesture-wave'])).toEqual({})
    expect(parseManifest('wave.vrma')).toEqual({})
  })
})

describe('armTracksOnly', () => {
  it('keeps arm tracks and discards the head, spine and face', () => {
    const arms = new Set(['Normalized_L_UpperArm', 'Normalized_R_Hand'])
    const tracks = [
      { name: 'Normalized_L_UpperArm.quaternion' },
      { name: 'Normalized_Head.quaternion' },
      { name: 'Normalized_R_Hand.quaternion' },
      { name: 'Normalized_Spine.position' },
      { name: 'happy.weight' },
    ]
    expect(armTracksOnly(tracks, arms).map((track) => track.name)).toEqual([
      'Normalized_L_UpperArm.quaternion',
      'Normalized_R_Hand.quaternion',
    ])
  })

  it('covers both arms down to the fingertips and nothing above the shoulder', () => {
    expect(ARM_BONES).toContain('leftShoulder')
    expect(ARM_BONES).toContain('rightLittleDistal')
    expect(ARM_BONES).not.toContain('head')
    expect(ARM_BONES).not.toContain('spine')
  })
})
