/**
 * The motion player.
 *
 * Motions are additive oscillations over the held pose, and they die away on
 * their own -- people nod twice and stop, they do not metronome.
 */

import { describe, expect, it } from 'vitest'
import type { VRM } from '@pixiv/three-vrm'

import { applyMotion } from './rig'

function fakeVrm(): { vrm: VRM; bones: Record<string, { rotation: { x: number; y: number; z: number } }> } {
  const bones: Record<string, { rotation: { x: number; y: number; z: number } }> = {}
  const humanoid = {
    getNormalizedBoneNode: (name: string) => {
      bones[name] ??= { rotation: { x: 0, y: 0, z: 0 } }
      return bones[name]
    },
  }
  return { vrm: { humanoid } as unknown as VRM, bones }
}

describe('applyMotion', () => {
  it('nods about the pitch axis', () => {
    const { vrm, bones } = fakeVrm()
    applyMotion(vrm, 'nod', 0.15)
    expect(Math.abs(bones['head']?.rotation.x ?? 0)).toBeGreaterThan(0)
    expect(bones['head']?.rotation.y).toBe(0)
  })

  it('shakes about the yaw axis', () => {
    const { vrm, bones } = fakeVrm()
    applyMotion(vrm, 'shake', 0.1)
    expect(Math.abs(bones['head']?.rotation.y ?? 0)).toBeGreaterThan(0)
  })

  it('waves with the forearm, not the head', () => {
    const { vrm, bones } = fakeVrm()
    applyMotion(vrm, 'wave', 0.1)
    expect(Math.abs(bones['rightLowerArm']?.rotation.y ?? 0)).toBeGreaterThan(0)
    expect(bones['head']).toBeUndefined()
  })

  it('dies away instead of nodding forever', () => {
    const { vrm, bones } = fakeVrm()
    applyMotion(vrm, 'nod', 6)
    expect(bones['head']?.rotation.x ?? 0).toBe(0)
  })

  it('adds to the pose rather than replacing it', () => {
    const { vrm, bones } = fakeVrm()
    const head = vrm.humanoid.getNormalizedBoneNode('head')
    if (head) head.rotation.x = 0.5
    applyMotion(vrm, 'nod', 0.15)
    expect(bones['head']?.rotation.x).not.toBe(0.5)
    expect(bones['head']?.rotation.x ?? 0).toBeGreaterThan(0.3)
  })
})
