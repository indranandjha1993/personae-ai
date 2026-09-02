/**
 * Detects the listener speaking over a reply.
 *
 * The microphone hears the reply through the speakers, so a bare amplitude
 * threshold interrupts her constantly. Input must be clearly louder than what
 * is playing, and stay that way, before it counts as someone talking.
 */

/** How much louder than the playback the input must be. */
const MARGIN = 2.5

/** Absolute floor, so room noise never triggers on its own. */
const NOISE_FLOOR = 0.02

/** Consecutive loud frames required, at ~100ms each. */
const SUSTAINED_FRAMES = 3

export class BargeInDetector {
  private loudFrames = 0

  /**
   * Returns true when the input has been clearly louder than the playback for
   * long enough to be speech rather than a cough or an echo.
   */
  observe(inputLevel: number, playbackLevel: number): boolean {
    const threshold = Math.max(NOISE_FLOOR, playbackLevel * MARGIN)
    if (inputLevel < threshold) {
      this.loudFrames = 0
      return false
    }
    this.loudFrames += 1
    if (this.loudFrames < SUSTAINED_FRAMES) return false
    this.loudFrames = 0
    return true
  }

  reset(): void {
    this.loudFrames = 0
  }
}

/** Root-mean-square level of a PCM frame, normalised to 0..1. */
export function frameLevel(frame: Int16Array): number {
  if (frame.length === 0) return 0
  let sum = 0
  for (let i = 0; i < frame.length; i += 1) {
    const sample = (frame[i] ?? 0) / 0x8000
    sum += sample * sample
  }
  return Math.sqrt(sum / frame.length)
}
