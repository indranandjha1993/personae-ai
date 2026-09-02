/**
 * Mouth shapes from the sound of her voice.
 *
 * No provider gives phoneme timing, so the shape is inferred from the audio
 * that is playing. Rather than picking one viseme per frame -- which flickers
 * at every boundary -- openness and frontness are treated as a continuous
 * plane, and the five vowel morphs are blended across it. The jaw follows
 * loudness on a fast constant while vowel identity settles slowly, so the mouth
 * can be responsive without being twitchy.
 */

import type { AudioFeatures } from '../audio/playback'

export interface LipWeights {
  aa: number
  ih: number
  ou: number
  ee: number
  oh: number
  lipW: number
  jaw: number
  wide: number
  rest: number
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value))

const smoothstep = (low: number, high: number, value: number): number => {
  const t = clamp01((value - low) / (high - low))
  return t * t * (3 - 2 * t)
}

/** Frame-rate independent chase, quicker to open than to close. */
const chase = (current: number, target: number, delta: number, up: number, down: number): number =>
  current + (target - current) * (1 - Math.exp(-delta / (target > current ? up : down)))

const JAW_ATTACK = 0.03
const JAW_RELEASE = 0.09
const VOWEL_ATTACK = 0.05
const VOWEL_RELEASE = 0.12
const FEATURE_TAU = 0.07

/** Hold the shape through stop consonants rather than chattering shut. */
const SILENCE_GRACE = 0.14
/**
 * Lips parted at rest; a closed seam reads as no mouth at all. Tuned for the
 * upper-body framing, where the face is half the size it was in the portrait.
 */
const JAW_AT_REST = 0.16
const JAW_MAX = 0.55
/** Stacked morphs distort the mesh past this. */
const VOWEL_CAP = 0.85

export class LipSync {
  private readonly weights: LipWeights = {
    aa: 0, ih: 0, ou: 0, ee: 0, oh: 0, lipW: 0, jaw: JAW_AT_REST, wide: 0, rest: 0,
  }
  private frontness = 0.5
  private openness = 0
  private quiet = 0

  /** Seconds of continuous near-silence, which stands in for a clause break. */
  get pauseSeconds(): number {
    return this.quiet
  }

  update(features: AudioFeatures, delta: number, widthBias = 0): LipWeights {
    const speaking = features.voiced > 0.02 || features.sibilance > 0.3
    this.quiet = speaking ? 0 : this.quiet + delta

    const k = 1 - Math.exp(-delta / FEATURE_TAU)
    this.frontness += (features.frontness - this.frontness) * k
    const openTarget =
      clamp01(0.65 * Math.min(1, features.rms / 0.09) ** 0.7 + 0.35 * features.openness) *
      features.voiced
    this.openness += (openTarget - this.openness) * k

    const target = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0, lipW: 0, jaw: JAW_AT_REST, wide: 0 }

    if (speaking || this.quiet < SILENCE_GRACE) {
      const open = smoothstep(0.45, 0.75, this.openness)
      const close = 1 - smoothstep(0.2, 0.5, this.openness)
      const mid = Math.max(0, 1 - open - close)

      target.aa = open
      target.ee = mid * this.frontness
      target.oh = mid * (1 - this.frontness)
      target.ih = close * this.frontness * features.voiced
      target.ou = close * (1 - this.frontness) * features.voiced

      const sum = target.aa + target.ee + target.oh + target.ih + target.ou
      if (sum > VOWEL_CAP) {
        const scale = VOWEL_CAP / sum
        target.aa *= scale
        target.ee *= scale
        target.oh *= scale
        target.ih *= scale
        target.ou *= scale
      }

      target.jaw = JAW_AT_REST + (JAW_MAX - JAW_AT_REST) * this.openness
      target.wide = clamp01(0.4 * this.frontness * features.voiced + widthBias)
      target.lipW = 0.5 * (1 - this.frontness) * close * features.voiced

      // Hiss carries little energy but the mouth stays shaped: teeth close,
      // lips spread. Without this the jaw drops on every "s".
      if (features.sibilance > 0.25 && features.voiced < 0.35) {
        target.aa = 0
        target.oh = 0
        target.ou = 0
        target.lipW = 0
        target.ih = Math.max(target.ih, 0.2)
        target.jaw = Math.min(target.jaw, 0.12)
        target.wide = Math.max(target.wide, 0.3)
      }
    }

    const w = this.weights
    w.aa = chase(w.aa, target.aa, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.ih = chase(w.ih, target.ih, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.ou = chase(w.ou, target.ou, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.ee = chase(w.ee, target.ee, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.oh = chase(w.oh, target.oh, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.lipW = chase(w.lipW, target.lipW, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.jaw = chase(w.jaw, target.jaw, delta, JAW_ATTACK, JAW_RELEASE)
    w.wide = chase(w.wide, target.wide, delta, VOWEL_ATTACK, VOWEL_RELEASE)
    w.rest = chase(w.rest, this.quiet > 1.5 ? 0.1 : 0, delta, 0.4, 0.4)

    // Each vowel is smoothed on its own, so the total can drift above the cap
    // while one is still rising and another has not yet fallen.
    const blended = w.aa + w.ih + w.ou + w.ee + w.oh
    if (blended > VOWEL_CAP) {
      const scale = VOWEL_CAP / blended
      w.aa *= scale
      w.ih *= scale
      w.ou *= scale
      w.ee *= scale
      w.oh *= scale
    }
    return w
  }
}
