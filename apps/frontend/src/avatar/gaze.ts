/**
 * Where she looks.
 *
 * Eye contact is the strongest presence cue a talking head has, and gaze
 * carries conversational meaning: people look away when they take the floor or
 * think, and back when they hand it over. Saccades are ballistic -- a fixed
 * flight along a position curve, never damped, or they read as a slow drift.
 */

import type { Activity } from './expression-map'

interface Saccade {
  fromYaw: number
  fromPitch: number
  toYaw: number
  toPitch: number
  elapsed: number
  duration: number
}

const rand = (lo: number, hi: number): number => lo + Math.random() * (hi - lo)
const ease = (t: number): number => {
  const c = Math.min(1, Math.max(0, t))
  return c * c * (3 - 2 * c)
}

/** Saccadic main sequence: about 21ms plus 2.2ms per degree travelled. */
const flightTime = (degrees: number): number => 0.021 + 0.0022 * degrees

/** Where the eyes go when they leave the camera, in degrees. */
const AVERSION: Record<Activity, () => { yaw: number; pitch: number }> = {
  idle: () => ({ yaw: rand(-10, 10), pitch: rand(-4, 4) }),
  listening: () => ({ yaw: rand(3, 7) * (Math.random() < 0.5 ? -1 : 1), pitch: rand(-8, -4) }),
  // Up and to one side: the classic thinking glance.
  thinking: () => ({ yaw: rand(8, 16) * (Math.random() < 0.56 ? 1 : -1), pitch: rand(5, 11) }),
  speaking: () => ({ yaw: rand(4, 10) * (Math.random() < 0.5 ? -1 : 1), pitch: rand(-6, 2) }),
  error: () => ({ yaw: rand(-3, 3), pitch: rand(-8, -5) }),
}

/** How long each state holds contact, holds aversion, and how readily it looks away. */
const TIMING: Record<Activity, { contact: [number, number]; avert: [number, number]; pAvert: number }> = {
  idle: { contact: [2.0, 5.0], avert: [0.6, 1.5], pAvert: 0.25 },
  // Listeners hold contact most of the time.
  listening: { contact: [2.5, 6.0], avert: [0.4, 0.9], pAvert: 0.15 },
  // Cognitive load pulls the eyes away.
  thinking: { contact: [0.5, 1.2], avert: [1.2, 3.0], pAvert: 0.8 },
  speaking: { contact: [1.0, 2.5], avert: [0.5, 1.2], pAvert: 0.45 },
  error: { contact: [1.5, 3.0], avert: [0.8, 1.5], pAvert: 0.4 },
}

export class GazeController {
  private averted = false
  private yaw = 0
  private pitch = 0
  private saccade: Saccade | null = null
  private nextDecision = 1.5
  private nextMicro = 1.0
  private clock = 0
  private previous: Activity = 'idle'

  /** Degrees travelled by a saccade launched this frame; blinks follow large ones. */
  lastSaccadeDegrees = 0

  update(activity: Activity, delta: number, pauseSeconds: number, accented: boolean): {
    yaw: number
    pitch: number
  } {
    this.clock += delta
    this.lastSaccadeDegrees = 0
    const timing = TIMING[activity]

    if (activity !== this.previous) {
      this.onActivityChange(activity)
      this.previous = activity
    }

    // A gap in speech is a clause boundary: glance back at the listener.
    if (activity === 'speaking' && this.averted && pauseSeconds > 0.35 && pauseSeconds < 0.42) {
      this.toContact(rand(1.0, 2.0))
    }
    // Speakers meet your eyes on the words they mean.
    if (accented && this.averted && Math.random() < 0.5) {
      this.toContact(rand(1.0, 2.5))
    }

    if (this.clock >= this.nextDecision && !this.saccade) {
      if (!this.averted && Math.random() < timing.pAvert) {
        this.toAversion(activity, rand(...timing.avert))
      } else {
        this.toContact(rand(...timing.contact))
      }
    }

    // Microsaccades: the eye is never still, even mid-fixation.
    if (this.clock >= this.nextMicro && !this.saccade) {
      const size = rand(0.3, 1.0)
      const angle = rand(0, Math.PI * 2)
      this.launch(this.yaw + Math.cos(angle) * size, this.pitch + Math.sin(angle) * size * 0.6)
      this.nextMicro = this.clock + rand(0.6, 2.2)
    }

    this.advance(delta)
    return { yaw: this.yaw, pitch: this.pitch }
  }

  private onActivityChange(activity: Activity): void {
    if (activity === 'speaking') {
      // Taking the floor: most people look away as they start.
      if (Math.random() < 0.7) this.toAversion('speaking', rand(0.6, 1.4))
      return
    }
    if (this.previous === 'speaking') {
      // Handing the floor back: contact is the turn-yielding signal.
      this.toContact(rand(1.5, 2.5))
      return
    }
    if (activity === 'thinking') this.toAversion('thinking', rand(1.2, 3.0))
  }

  private toContact(hold: number): void {
    this.averted = false
    this.launch(0, 0)
    this.nextDecision = this.clock + hold
  }

  private toAversion(activity: Activity, hold: number): void {
    this.averted = true
    const target = AVERSION[activity]()
    this.launch(target.yaw, target.pitch)
    this.nextDecision = this.clock + hold
  }

  private launch(toYaw: number, toPitch: number): void {
    const degrees = Math.hypot(toYaw - this.yaw, toPitch - this.pitch)
    if (degrees < 0.1) return
    this.saccade = {
      fromYaw: this.yaw,
      fromPitch: this.pitch,
      toYaw,
      toPitch,
      elapsed: 0,
      duration: flightTime(degrees),
    }
    this.lastSaccadeDegrees = degrees
  }

  private advance(delta: number): void {
    const flight = this.saccade
    if (!flight) return
    flight.elapsed += delta
    const t = flight.elapsed / flight.duration
    if (t >= 1) {
      this.yaw = flight.toYaw
      this.pitch = flight.toPitch
      this.saccade = null
      return
    }
    const e = ease(t)
    this.yaw = flight.fromYaw + (flight.toYaw - flight.fromYaw) * e
    this.pitch = flight.fromPitch + (flight.toPitch - flight.fromPitch) * e
  }
}
