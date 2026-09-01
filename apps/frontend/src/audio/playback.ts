/**
 * Gapless playback of streamed PCM.
 *
 * Chunks arrive over a WebSocket at irregular intervals, so each one is
 * scheduled against the AudioContext clock rather than played on arrival.
 * Starting every buffer at `currentTime` would leave audible gaps whenever the
 * network hiccuped; tracking the end of the previous chunk instead keeps
 * playback continuous.
 */

/** How far ahead of `currentTime` to start, absorbing network jitter. */
const LEAD_SECONDS = 0.08

export class PcmPlayer {
  private nextStartTime = 0
  private readonly sources = new Set<AudioBufferSourceNode>()

  constructor(private readonly context: AudioContext) {}

  /** Schedule one chunk of 16-bit PCM immediately after whatever precedes it. */
  enqueue(samples: Int16Array): void {
    if (samples.length === 0) return

    const buffer = this.context.createBuffer(1, samples.length, this.context.sampleRate)
    buffer.getChannelData(0).set(this.toFloat(samples))

    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.connect(this.context.destination)

    // If the stream stalled long enough for the schedule to fall behind the
    // clock, restart from now rather than trying to catch up on stale audio.
    const earliest = this.context.currentTime + LEAD_SECONDS
    const startAt = Math.max(this.nextStartTime, earliest)

    source.start(startAt)
    this.nextStartTime = startAt + buffer.duration

    this.sources.add(source)
    source.onended = () => this.sources.delete(source)
  }

  /** Convert 16-bit samples to the normalised floats Web Audio expects. */
  toFloat(samples: Int16Array): Float32Array {
    const floats = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i += 1) {
      // Asymmetric ranges: negative samples divide by 32768, positive by 32767.
      const sample = samples[i] ?? 0
      floats[i] = sample < 0 ? sample / 0x8000 : sample / 0x7fff
    }
    return floats
  }

  /** Stop everything still scheduled and clear the timeline. */
  stop(): void {
    for (const source of this.sources) {
      try {
        source.stop()
      } catch {
        // Already ended; nothing to stop.
      }
    }
    this.sources.clear()
    this.nextStartTime = 0
  }
}
