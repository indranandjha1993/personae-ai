/**
 * Gapless playback of streamed PCM.
 *
 * Chunks arrive over a WebSocket at irregular intervals, so each one is
 * scheduled against the AudioContext clock rather than played on arrival.
 * Starting every buffer at `currentTime` would leave audible gaps whenever the
 * network hiccuped; tracking the end of the previous chunk instead keeps
 * playback continuous.
 *
 * The source rate is supplied separately from the output device rate. Labelling
 * 24kHz speech with a 48kHz context rate plays it at double speed, which sounds
 * like a chipmunk; the browser resamples for us once the buffer is honest about
 * what it contains.
 */

/** How far ahead of `currentTime` to start, absorbing network jitter. */
const LEAD_SECONDS = 0.08

export class PcmPlayer {
  private nextStartTime = 0
  private readonly sources = new Set<AudioBufferSourceNode>()
  private readonly analyser: AnalyserNode | null
  private readonly frame: Float32Array<ArrayBuffer>

  constructor(
    private readonly context: AudioContext,
    private readonly sourceSampleRate: number,
  ) {
    // Everything routes through an analyser so the avatar's mouth can follow
    // the audio that is actually playing. Reading loudness from playback keeps
    // the mouth in sync by construction -- it cannot drift from the sound.
    this.analyser = typeof context.createAnalyser === 'function' ? context.createAnalyser() : null
    if (this.analyser) {
      this.analyser.fftSize = 1024
      this.analyser.connect(context.destination)
    }
    this.frame = new Float32Array(new ArrayBuffer((this.analyser?.fftSize ?? 0) * 4))
  }

  /** Root-mean-square loudness of what is playing right now, 0 when silent. */
  currentLoudness(): number {
    if (!this.analyser) return 0
    this.analyser.getFloatTimeDomainData(this.frame)
    let sum = 0
    for (let i = 0; i < this.frame.length; i += 1) {
      const sample = this.frame[i] ?? 0
      sum += sample * sample
    }
    return Math.sqrt(sum / this.frame.length)
  }

  /** Schedule one chunk of 16-bit PCM immediately after whatever precedes it. */
  enqueue(samples: Int16Array): void {
    if (samples.length === 0) return

    const buffer = this.context.createBuffer(1, samples.length, this.sourceSampleRate)
    buffer.getChannelData(0).set(this.toFloat(samples))

    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.connect(this.analyser ?? this.context.destination)

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
