/**
 * Captures microphone audio and posts 16-bit PCM frames to the main thread.
 *
 * Runs on the audio rendering thread, so it must not allocate more than
 * necessary or block. Float samples are converted here rather than on the main
 * thread so only compact buffers cross the message port.
 *
 * Kept as plain .js: Vite is configured not to inline this file, because
 * AudioWorklet.addModule() rejects base64 data: URIs in Safari and Firefox.
 */

const FRAME_SAMPLES = 1600 // 100 ms at 16 kHz

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Int16Array(FRAME_SAMPLES)
    this.offset = 0
  }

  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel) return true

    for (let i = 0; i < channel.length; i += 1) {
      // Clamp before scaling: values outside [-1, 1] would wrap on conversion.
      const sample = Math.max(-1, Math.min(1, channel[i]))
      this.buffer[this.offset] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      this.offset += 1

      if (this.offset === FRAME_SAMPLES) {
        // Transfer a copy: the buffer is reused for the next frame.
        const frame = this.buffer.slice()
        this.port.postMessage(frame, [frame.buffer])
        this.offset = 0
      }
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor)
