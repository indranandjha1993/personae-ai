import { describe, expect, it } from 'vitest'

import { GesturePhaser } from './gesture-timing'

const FRAME = 1 / 60

const run = (phaser: GesturePhaser, seconds: number, accent = 0) => {
  let last = phaser.update(FRAME, accent)
  for (let t = FRAME; t < seconds; t += FRAME) last = phaser.update(FRAME, 0)
  return last
}

describe('GesturePhaser', () => {
  it('prepares part way and strikes on the first stressed syllable', () => {
    const phaser = new GesturePhaser()
    phaser.begin()
    const prepared = run(phaser, 0.2)
    expect(prepared.phase).toBe('prepare')
    expect(prepared.amount).toBeGreaterThan(0)
    expect(prepared.amount).toBeLessThan(1)

    const struck = phaser.update(FRAME, 0.8)
    expect(struck.phase).toBe('stroke')
    expect(struck.amount).toBe(1)
    // The stroke is quick; the preparation was not.
    expect(struck.ease).toBeGreaterThan(prepared.ease)
  })

  it('does not wait forever for a stress that never comes', () => {
    const phaser = new GesturePhaser()
    phaser.begin()
    expect(run(phaser, 0.7).amount).toBe(1)
  })

  it('settles into a hold after the stroke', () => {
    const phaser = new GesturePhaser()
    phaser.begin()
    phaser.update(FRAME, 1)
    expect(run(phaser, 0.4).phase).toBe('hold')
  })

  it('beats on later stresses while holding, then goes still', () => {
    const phaser = new GesturePhaser()
    phaser.begin()
    phaser.update(FRAME, 1)
    run(phaser, 0.4)
    const beat = phaser.update(FRAME, 0.7).beat
    const later = run(phaser, 0.1).beat
    const gone = run(phaser, 0.4).beat
    expect(beat).toBeGreaterThan(0)
    expect(later).toBeGreaterThan(0)
    expect(gone).toBe(0)
  })

  it('gives nothing at rest', () => {
    const phaser = new GesturePhaser()
    phaser.begin()
    phaser.update(FRAME, 1)
    phaser.release()
    const rest = phaser.update(FRAME, 1)
    expect(rest).toMatchObject({ amount: 0, beat: 0, phase: 'rest' })
  })
})
