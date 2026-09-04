/**
 * Detects the listener speaking over a reply, from the microphone alone.
 *
 * The recogniser is the authoritative signal and stops her on the server;
 * this is the fast local path that halts playback before that round trip.
 * The microphone hears only a fraction of what is played, less again with
 * echo cancellation, so the bar is a fraction of the playback level with a
 * floor for room noise, held long enough to be a voice and not a cough.
 */

/** Absolute floor, so room noise never triggers on its own. */
const NOISE_FLOOR = 0.04

/**
 * What fraction of the playback level counts as echo rather than speech.
 *
 * With echo cancellation on, the reply leaks back at a small fraction of its
 * own level; a voice in the room lands well above this.
 */
const ECHO_RATIO = 0.6

/** Consecutive loud frames required, at 80ms each: about a quarter second. */
const SUSTAINED_FRAMES = 3

export class BargeInDetector {
  private loudFrames = 0

  /**
   * Returns true when the input has been clearly louder than the echo of the
   * playback for long enough to be speech rather than a cough.
   */
  observe(inputLevel: number, playbackLevel: number): boolean {
    // Nothing playing means nothing to interrupt.
    if (playbackLevel <= 0) {
      this.loudFrames = 0
      return false
    }
    const threshold = Math.max(NOISE_FLOOR, playbackLevel * ECHO_RATIO)
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
