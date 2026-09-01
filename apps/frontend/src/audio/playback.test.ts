import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PcmPlayer } from './playback'

/** Minimal AudioContext double that records how sources were scheduled. */
class FakeContext {
  currentTime = 0
  // Browsers commonly run the output device at 48kHz, while the speech
  // provider streams 24kHz. The two must not be conflated.
  sampleRate = 48_000
  destination = {} as AudioDestinationNode
  readonly starts: number[] = []

  readonly bufferRates: number[] = []

  createBuffer(channels: number, length: number, rate: number) {
    this.bufferRates.push(rate)
    return {
      numberOfChannels: channels,
      length,
      sampleRate: rate,
      getChannelData: () => new Float32Array(length),
      duration: length / rate,
    } as unknown as AudioBuffer
  }

  createBufferSource() {
    const starts = this.starts
    return {
      buffer: null,
      connect: vi.fn(),
      start(when: number) {
        starts.push(when)
      },
      stop: vi.fn(),
    } as unknown as AudioBufferSourceNode
  }
}

describe('PcmPlayer', () => {
  let context: FakeContext

  beforeEach(() => {
    context = new FakeContext()
  })

  it('schedules the first chunk slightly ahead of now to absorb jitter', () => {
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    player.enqueue(new Int16Array(2400))
    expect(context.starts[0]).toBeGreaterThan(context.currentTime)
  })

  it('schedules consecutive chunks back to back, not all at once', () => {
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    player.enqueue(new Int16Array(2400)) // 100 ms at 24 kHz
    player.enqueue(new Int16Array(2400))
    const [first = 0, second = 0] = context.starts
    expect(second - first).toBeCloseTo(0.1, 5)
  })

  it('resets the schedule after a gap so playback does not lag behind', () => {
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    player.enqueue(new Int16Array(2400))
    context.currentTime = 10 // a long silence passed
    player.enqueue(new Int16Array(2400))
    expect(context.starts[1]).toBeGreaterThanOrEqual(10)
  })

  it('labels buffers with the source rate, not the output device rate', () => {
    // Regression: buffers were created at context.sampleRate, so 24kHz speech
    // played at 48kHz -- roughly double speed, and audibly chipmunked.
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    player.enqueue(new Int16Array(2400))
    expect(context.bufferRates[0]).toBe(24_000)
  })

  it('derives chunk duration from the source rate', () => {
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    player.enqueue(new Int16Array(2400)) // 100ms of 24kHz audio
    player.enqueue(new Int16Array(2400))
    const [first = 0, second = 0] = context.starts
    expect(second - first).toBeCloseTo(0.1, 5)
  })

  it('converts 16-bit samples to normalised floats', () => {
    const player = new PcmPlayer(context as unknown as AudioContext, 24_000)
    // Full-scale samples map to exactly +/-1, and silence to 0.
    expect(player.toFloat(new Int16Array([0, 32767, -32768]))).toEqual(
      new Float32Array([0, 1, -1]),
    )
  })
})
