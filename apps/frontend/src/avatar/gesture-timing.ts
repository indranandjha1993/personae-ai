/**
 * When a gesture moves, as distinct from what it looks like.
 *
 * A gesture prepares, strikes on the stressed word, holds while the point is
 * made, and comes down. Easing straight to the pose at the start of a
 * sentence gives the first of those and none of the others. The stroke waits
 * for the voice to stress a syllable; later stresses put a beat into the hand.
 */

export type Phase = 'rest' | 'prepare' | 'stroke' | 'hold'

/** How far toward the pose the hands travel before the stroke. */
const PREPARE_AMOUNT = 0.35
/** The stroke waits this long for a stressed syllable, then goes anyway. */
const PREPARE_MAX_SECONDS = 0.55
/** How long the stroke's quick travel lasts before the pose is merely held. */
const STROKE_SECONDS = 0.18
/** How long one beat pulse lasts. */
const BEAT_SECONDS = 0.22

/** How quickly the arms chase their target in each phase. */
const EASE: Record<Phase, number> = {
  rest: 3.2,
  prepare: 3.2,
  // Fast: a stroke that eases in is a drift, not a stroke.
  stroke: 11,
  hold: 3.2,
}

export interface GestureTiming {
  /** How far toward the gesture's pose the arms should be, 0 to 1. */
  amount: number
  /** A beat pulse on the leading hand, 0 to 1, on stresses while holding. */
  beat: number
  phase: Phase
  /** Rate constant for easing the arms this frame. */
  ease: number
}

export class GesturePhaser {
  private phase: Phase = 'rest'
  private since = 0
  private beatAt = -1

  /** A gesture has been cued for the sentence now being spoken. */
  begin(): void {
    this.phase = 'prepare'
    this.since = 0
    this.beatAt = -1
  }

  /** The hands come down. */
  release(): void {
    this.phase = 'rest'
    this.since = 0
    this.beatAt = -1
  }

  update(delta: number, accent: number): GestureTiming {
    this.since += delta

    if (this.phase === 'prepare' && (accent > 0 || this.since >= PREPARE_MAX_SECONDS)) {
      this.phase = 'stroke'
      this.since = 0
    } else if (this.phase === 'stroke' && this.since >= STROKE_SECONDS) {
      this.phase = 'hold'
      this.since = 0
    } else if (this.phase === 'hold' && accent > 0 && this.beatAt < 0) {
      this.beatAt = 0
    }

    let beat = 0
    if (this.beatAt >= 0) {
      this.beatAt += delta
      if (this.beatAt < BEAT_SECONDS) {
        beat = Math.sin((this.beatAt / BEAT_SECONDS) * Math.PI)
      } else {
        this.beatAt = -1
      }
    }

    const amount = this.phase === 'rest' ? 0 : this.phase === 'prepare' ? PREPARE_AMOUNT : 1
    return { amount, beat, phase: this.phase, ease: EASE[this.phase] }
  }
}
