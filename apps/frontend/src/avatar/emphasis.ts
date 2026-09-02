/**
 * Nods and brow motion on the words she stresses.
 *
 * A stressed syllable is loudness rising above its own recent average, which a
 * fast envelope compared against a slow one detects cheaply. Brows move
 * asymmetrically because a face that raises both by exactly the same amount
 * reads as a mask.
 */

export interface EmphasisFrame {
  /** Strength of an accent starting this frame, 0 when none. */
  accent: number
  browLeft: number
  browRight: number
  /** Radians to add to head pitch. */
  nod: number
}

const FAST_TAU = 0.06
const SLOW_TAU = 0.45
const THRESHOLD = 0.045
/** Roughly three accents a second at most, which is the stressed-syllable rate. */
const REFRACTORY = 0.35

const NOD_SECONDS = 0.37
const BROW_ATTACK = 0.08
const BROW_RELEASE = 0.4

export class EmphasisTracker {
  private fast = 0
  private slow = 0
  private sinceAccent = 1
  private nodProgress = 1
  private nodAmplitude = 0
  private browProgress = 1
  private browLeft = 0
  private browRight = 0
  private browHold = 0.15
  private bed = 0

  update(rms: number, delta: number, speaking: boolean): EmphasisFrame {
    this.fast += (rms - this.fast) * (1 - Math.exp(-delta / FAST_TAU))
    this.slow += (rms - this.slow) * (1 - Math.exp(-delta / SLOW_TAU))
    this.sinceAccent += delta

    let accent = 0
    const excess = this.fast - this.slow * 1.25
    if (speaking && excess > THRESHOLD && this.sinceAccent > REFRACTORY) {
      accent = Math.min(1, excess / 0.12)
      this.sinceAccent = 0
      this.startNod(accent)
      if (Math.random() < 0.6) this.startBrow(accent)
    }

    return {
      accent,
      browLeft: Math.min(1, this.bedLevel(delta, speaking) + this.browLeft * this.browEnvelope()),
      browRight: Math.min(1, this.bed + this.browRight * this.browEnvelope()),
      nod: this.nodValue(delta),
    }
  }

  private startNod(accent: number): void {
    this.nodProgress = 0
    this.nodAmplitude = 0.025 + 0.035 * accent
  }

  private startBrow(accent: number): void {
    const skew = Math.random()
    const amplitude = 0.25 + 0.25 * accent
    this.browProgress = 0
    if (Math.random() < 0.15) {
      // A single raised brow: the "really?" look.
      this.browLeft = skew < 0.5 ? amplitude : 0
      this.browRight = skew < 0.5 ? 0 : amplitude
      this.browHold = 0.7
      return
    }
    this.browLeft = amplitude * (0.8 + 0.4 * skew)
    this.browRight = amplitude * (1.2 - 0.4 * skew)
    this.browHold = 0.15
  }

  /** Down quickly, back up slowly, the way a real nod moves. */
  private nodValue(delta: number): number {
    this.nodProgress = Math.min(1, this.nodProgress + delta / NOD_SECONDS)
    const t = this.nodProgress
    if (t >= 1) return 0
    return this.nodAmplitude *
      (t < 0.32 ? Math.sin((t / 0.32) * (Math.PI / 2)) : Math.cos(((t - 0.32) / 0.68) * (Math.PI / 2)))
  }

  private browEnvelope(): number {
    const duration = BROW_ATTACK + this.browHold + BROW_RELEASE
    if (this.browProgress >= 1) return 0
    const t = this.browProgress * duration
    if (t < BROW_ATTACK) return t / BROW_ATTACK
    if (t < BROW_ATTACK + this.browHold) return 1
    return Math.max(0, 1 - (t - BROW_ATTACK - this.browHold) / BROW_RELEASE)
  }

  /** Brows ride a little high while she is talking, and settle when she stops. */
  private bedLevel(delta: number, speaking: boolean): number {
    const duration = BROW_ATTACK + this.browHold + BROW_RELEASE
    this.browProgress = Math.min(1, this.browProgress + delta / duration)
    const target = speaking ? 0.08 + 1.2 * Math.min(0.1, this.slow) : 0
    this.bed += (target - this.bed) * (1 - Math.exp(-delta / 0.6))
    return this.bed
  }
}
