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

/** A per-frame read of what the voice is doing right now. */
export interface AudioFeatures {
  /** Loudness, 0 to 1. */
  rms: number
  /** 0 for back rounded vowels (oo, oh), 1 for front spread ones (ee, ih). */
  frontness: number
  /** How open the jaw reads from the first formant, 0 to 1. */
  openness: number
  /** Proportion of energy in the hiss bands, which marks s and sh. */
  sibilance: number
  /** Voicing gate, 0 to 1. */
  voiced: number
}

export const SILENT_FEATURES: AudioFeatures = Object.freeze({
  rms: 0,
  frontness: 0.5,
  openness: 0,
  sibilance: 0,
  voiced: 0,
})

/**
 * Frequency bands in hertz: voicing, the two first-formant ranges that separate
 * close from open vowels, the two second-formant ranges that separate back from
 * front, and the hiss band.
 */
const BAND_HZ: readonly (readonly [number, number])[] = [
  [85, 255],
  [250, 450],
  [550, 950],
  [700, 1300],
  [1650, 2600],
  [4200, 8000],
]

export class PcmPlayer {
  private nextStartTime = 0
  private readonly sources = new Set<AudioBufferSourceNode>()
  private readonly analyser: AnalyserNode | null
  private readonly frame: Float32Array<ArrayBuffer>
  private readonly spectrum: Uint8Array<ArrayBuffer>
  private readonly bands: [number, number][]

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

    if (this.analyser) {
      // The default smears consonant transitions; the mapper does its own
      // asymmetric smoothing downstream.
      this.analyser.smoothingTimeConstant = 0.5
    }
    const binCount = this.analyser?.frequencyBinCount ?? 0
    this.spectrum = new Uint8Array(new ArrayBuffer(binCount))
    // Derived from the context, not the source: the graph runs at the device
    // rate and resamples the 24kHz buffers into it.
    const hzPerBin = context.sampleRate / (this.analyser?.fftSize ?? 1024)
    this.bands = BAND_HZ.map(([low, high]) => [
      Math.max(1, Math.round(low / hzPerBin)),
      Math.min(Math.max(binCount - 1, 1), Math.round(high / hzPerBin)),
    ])
  }

  /**
   * True once everything scheduled has finished playing.
   *
   * Loudness cannot answer this: audio is scheduled ahead of real time, so the
   * player is silent for a moment before the first chunk sounds, and silent
   * again in the gap between sentences.
   */
  isFinished(): boolean {
    return this.sources.size === 0 && this.nextStartTime <= this.context.currentTime
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

  /** Read the current spectral shape into `out`, avoiding a per-frame allocation. */
  readFeatures(out: AudioFeatures): AudioFeatures {
    if (!this.analyser) return Object.assign(out, SILENT_FEATURES)
    out.rms = this.currentLoudness()
    this.analyser.getByteFrequencyData(this.spectrum)

    const energy = this.bands.map(([low, high]) => {
      let sum = 0
      for (let i = low; i <= high; i += 1) {
        const value = (this.spectrum[i] ?? 0) / 255
        sum += value * value
      }
      return sum / Math.max(1, high - low + 1)
    })

    const epsilon = 1e-4
    const [, f1low = 0, f1high = 0, f2low = 0, f2high = 0, hiss = 0] = energy
    const total = energy.reduce((a, b) => a + b, 0) + epsilon

    out.frontness = f2high / (f2high + f2low + epsilon)
    out.openness = f1high / (f1low + f1high + epsilon)
    out.sibilance = hiss / total
    out.voiced = Math.min(1, Math.max(0, (out.rms - 0.008) / 0.042))
    return out
  }

  /** When the audio queued so far will have finished, on the context clock. */
  get scheduledUntil(): number {
    return this.nextStartTime
  }

  /** The context clock, so callers can compare against scheduled times. */
  get now(): number {
    return this.context.currentTime
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
