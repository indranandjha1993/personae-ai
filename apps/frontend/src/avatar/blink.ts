/**
 * Blinking.
 *
 * A lid closes fast and opens slowly; snapping shut in a single frame reads as
 * a glitch. Blinks also cluster around gaze shifts and clause boundaries rather
 * than falling at random, which is what makes them look like punctuation
 * instead of a metronome.
 */

import type { Activity } from './expression-map'

const CLOSE_SECONDS = 0.07
const HOLD_SECONDS = 0.04
const OPEN_SECONDS = 0.18
const TOTAL = CLOSE_SECONDS + HOLD_SECONDS + OPEN_SECONDS

/** Mean seconds between blinks. Concentration suppresses them; speech invites them. */
const MEAN_INTERVAL: Record<Activity, number> = {
  idle: 4.5,
  listening: 3.6,
  thinking: 6.5,
  speaking: 3.2,
  error: 4.0,
}

const MIN_GAP = 0.8

const ease = (t: number): number => t * t * (3 - 2 * t)

export class BlinkController {
  private elapsed = Infinity
  private nextAt = 2
  private clock = 0
  private doubleQueued = false
  private lastBlinkAt = -Infinity
  private activity: Activity = 'idle'

  /** A large gaze shift usually drags a blink along with it. */
  onSaccade(degrees: number): void {
    if (degrees > 8) this.maybeBlink(0.35)
  }

  /** Blinks cluster at clause boundaries, the way punctuation does. */
  onPause(pauseSeconds: number): void {
    if (pauseSeconds > 0.3 && pauseSeconds < 0.38) this.maybeBlink(0.5)
  }

  onActivity(activity: Activity): void {
    if (this.activity === 'thinking' && activity === 'speaking') this.maybeBlink(0.7)
    this.activity = activity
  }

  /**
   * Returns lid closure, 0 open to 1 shut.
   *
   * `squint` is how far an expression has already narrowed the eyes, so a blink
   * on top of a smile travels only the remaining distance instead of mashing
   * the lids past closed.
   */
  update(delta: number, activity: Activity, squint: number): number {
    this.clock += delta
    this.activity = activity
    this.elapsed += delta

    if (this.clock >= this.nextAt) this.start()

    if (this.elapsed >= TOTAL) {
      if (this.doubleQueued) {
        this.doubleQueued = false
        this.elapsed = 0
      } else {
        return 0
      }
    }

    return this.envelope() * (1 - 0.5 * squint)
  }

  private envelope(): number {
    const t = this.elapsed
    if (t < CLOSE_SECONDS) return ease(t / CLOSE_SECONDS)
    if (t < CLOSE_SECONDS + HOLD_SECONDS) return 1
    return 1 - ease((t - CLOSE_SECONDS - HOLD_SECONDS) / OPEN_SECONDS)
  }

  private maybeBlink(probability: number): void {
    if (this.elapsed < TOTAL) return
    if (this.clock - this.lastBlinkAt < MIN_GAP) return
    if (Math.random() >= probability) return
    this.start()
  }

  private start(): void {
    this.elapsed = 0
    this.lastBlinkAt = this.clock
    // Real blinks occasionally come in pairs.
    this.doubleQueued = Math.random() < 0.12
    this.schedule()
  }

  private schedule(): void {
    // Exponential intervals: irregular, but never strobing and never absent.
    const gap = -Math.log(1 - Math.random()) * MEAN_INTERVAL[this.activity]
    this.nextAt = this.clock + Math.min(9, Math.max(1.2, gap))
  }
}
