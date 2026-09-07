import { afterEach, describe, expect, it, vi } from 'vitest'

import { BlinkController } from './blink'
import type { Activity } from './expression-map'
import { GazeController } from './gaze'

const run = (fn: (dt: number) => void, seconds: number, dt = 1 / 60): void => {
  for (let t = 0; t < seconds; t += dt) fn(dt)
}

const FRAME = 1 / 60

/**
 * A controller already looking away, with every coin-flip inside it decided.
 *
 * Aversion is what the clause-boundary and stressed-word rules act on, and it
 * arrives by chance; fixing the rolls is what lets the two rules be tested at
 * all rather than sampled for statistically.
 */
const averted = (): GazeController => {
  const gaze = new GazeController()
  // Taking the floor averts on the first speaking frame at this roll.
  gaze.update('speaking', FRAME, 0, false)
  run((dt) => gaze.update('speaking', dt, 0, false), 0.1)
  return gaze
}

/**
 * How far off the camera the eyes are, sampled without disturbing them.
 *
 * The activity has to match whatever the caller has been running: arriving at
 * 'speaking' from anything else is itself a reason to look away, so a probe
 * that changed it would cause the aversion it went to measure.
 */
const offCamera = (gaze: GazeController, activity: Activity = 'speaking'): number =>
  Math.abs(gaze.update(activity, FRAME, 0, false).yaw)

describe('GazeController', () => {
  it('holds the camera by default', () => {
    const gaze = new GazeController()
    const { yaw, pitch } = gaze.update('listening', 1 / 60, 0, false)
    expect(Math.abs(yaw)).toBeLessThan(2)
    expect(Math.abs(pitch)).toBeLessThan(2)
  })

  it('looks away while thinking', () => {
    const gaze = new GazeController()
    let furthest = 0
    run((dt) => {
      const { yaw } = gaze.update('thinking', dt, 0, false)
      furthest = Math.max(furthest, Math.abs(yaw))
    }, 6)
    expect(furthest).toBeGreaterThan(5)
  })

  it('returns to the camera when it stops speaking', () => {
    const gaze = new GazeController()
    run((dt) => gaze.update('speaking', dt, 0, false), 3)
    let closest = Infinity
    run((dt) => {
      const { yaw, pitch } = gaze.update('idle', dt, 0, false)
      closest = Math.min(closest, Math.hypot(yaw, pitch))
    }, 2)
    expect(closest).toBeLessThan(1)
  })

  it('moves the eyes ballistically, not by drifting', () => {
    // A saccade of ten degrees should complete in well under a tenth of a second.
    const gaze = new GazeController()
    run((dt) => gaze.update('thinking', dt, 0, false), 0.5)
    let moved = 0
    run((dt) => {
      const before = gaze.update('thinking', dt, 0, false).yaw
      const after = gaze.update('thinking', dt, 0, false).yaw
      moved = Math.max(moved, Math.abs(after - before))
    }, 4)
    expect(moved).toBeGreaterThan(0.2)
  })

  it('never sends the eyes somewhere absurd', () => {
    const gaze = new GazeController()
    for (const activity of ['idle', 'listening', 'thinking', 'speaking', 'error'] as const) {
      run((dt) => {
        const { yaw, pitch } = gaze.update(activity, dt, 0, false)
        expect(Math.abs(yaw)).toBeLessThanOrEqual(25)
        expect(Math.abs(pitch)).toBeLessThanOrEqual(20)
      }, 8)
    }
  })
})

/**
 * The two rules that give gaze its conversational meaning.
 *
 * Both were unreachable until the caller passed the pause and the accent
 * through, so these cover the wiring as much as the behaviour: a controller
 * that only ever sees zero and false still passes every test above.
 */
describe('GazeController, listening to the conversation', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('glances back at the listener at a clause boundary', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    const gaze = new GazeController()
    gaze.update('speaking', FRAME, 0, false)
    run((dt) => gaze.update('speaking', dt, 0, false), 0.1)
    expect(offCamera(gaze)).toBeGreaterThan(2)

    gaze.update('speaking', FRAME, 0.36, false)
    run((dt) => gaze.update('speaking', dt, 0.36, false), 0.1)
    expect(offCamera(gaze)).toBeLessThan(1)
  })

  it('stays away through the middle of a clause', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    const gaze = averted()
    run((dt) => gaze.update('speaking', dt, 0.2, false), 0.2)
    expect(offCamera(gaze)).toBeGreaterThan(2)
  })

  it('takes a clause boundary as it passes, not any pause at all', () => {
    // The window is a couple of frames wide on a rising counter, so a pause
    // already well past it is a silence she is sitting in, not a comma.
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    const gaze = averted()
    run((dt) => gaze.update('speaking', dt, 1.5, false), 0.2)
    expect(offCamera(gaze)).toBeGreaterThan(2)
  })

  it('meets your eyes on the word she means', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    const gaze = averted()
    expect(offCamera(gaze)).toBeGreaterThan(2)

    gaze.update('speaking', FRAME, 0, true)
    run((dt) => gaze.update('speaking', dt, 0, false), 0.1)
    expect(offCamera(gaze)).toBeLessThan(1)
  })

  it('does not answer a stressed word while she is already looking at you', () => {
    // Half the time the accent is ignored; the other half it is already
    // contact, and neither should launch a saccade to where the eyes are.
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    const gaze = new GazeController()
    run((dt) => gaze.update('listening', dt, 0, true), 0.5)
    expect(offCamera(gaze, 'listening')).toBeLessThan(2)
  })
})

describe('BlinkController', () => {
  it('opens the lid more slowly than it closes it', () => {
    const blink = new BlinkController()
    const trace: number[] = []
    run((dt) => trace.push(blink.update(dt, 'idle', 0)), 12)

    const peak = trace.indexOf(Math.max(...trace))
    expect(Math.max(...trace)).toBeGreaterThan(0.9)

    let closing = 0
    for (let i = peak; i >= 0 && (trace[i] ?? 0) > 0.05; i -= 1) closing += 1
    let opening = 0
    for (let i = peak; i < trace.length && (trace[i] ?? 0) > 0.05; i += 1) opening += 1
    expect(opening).toBeGreaterThan(closing)
  })

  it('never snaps shut in a single frame', () => {
    const blink = new BlinkController()
    let previous = 0
    let biggestJump = 0
    run((dt) => {
      const lid = blink.update(dt, 'idle', 0)
      biggestJump = Math.max(biggestJump, Math.abs(lid - previous))
      previous = lid
    }, 20)
    expect(biggestJump).toBeLessThan(0.5)
  })

  it('leaves the eyes mostly open', () => {
    const blink = new BlinkController()
    let shut = 0
    let frames = 0
    run((dt) => {
      if (blink.update(dt, 'idle', 0) > 0.5) shut += 1
      frames += 1
    }, 30)
    expect(shut / frames).toBeLessThan(0.1)
  })

  it('does not force already-narrowed eyes past closed', () => {
    const blink = new BlinkController()
    let peak = 0
    run((dt) => { peak = Math.max(peak, blink.update(dt, 'idle', 1)) }, 12)
    expect(peak).toBeLessThanOrEqual(0.55)
  })
})
