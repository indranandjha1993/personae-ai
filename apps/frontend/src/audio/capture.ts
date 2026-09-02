/**
 * Microphone capture via AudioWorklet.
 *
 * ScriptProcessorNode is deprecated and runs on the main thread, so capture
 * happens in a worklet on the audio thread instead. A dedicated 16 kHz context
 * is used because that is what the speech recogniser expects; resampling here
 * is cheaper and more predictable than doing it downstream.
 */

const CAPTURE_SAMPLE_RATE = 16_000
const WORKLET_URL = '/pcm-capture.worklet.js'

export interface Capture {
  stop: () => void
}

/**
 * Start capturing, invoking `onFrame` with 100 ms of 16-bit PCM at a time.
 *
 * Must be called from a user gesture: browsers refuse to start an AudioContext
 * otherwise.
 */
export async function startCapture(onFrame: (frame: Int16Array) => void): Promise<Capture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: false,
      // Lifts a quiet or distant speaker rather than leaving the recogniser
      // to work from what little reaches the microphone.
      autoGainControl: true,
    },
  })

  const context = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE })
  try {
    await context.audioWorklet.addModule(WORKLET_URL)
  } catch (error) {
    // Release the microphone if the worklet fails to load, rather than
    // leaving the recording indicator on with nothing listening.
    stream.getTracks().forEach((track) => { track.stop() })
    await context.close()
    throw error
  }

  const source = context.createMediaStreamSource(stream)
  const worklet = new AudioWorkletNode(context, 'pcm-capture')
  worklet.port.onmessage = (event: MessageEvent<Int16Array>) => { onFrame(event.data) }
  source.connect(worklet)

  let stopped = false
  return {
    stop: () => {
      if (stopped) return
      stopped = true
      worklet.port.onmessage = null
      source.disconnect()
      worklet.disconnect()
      stream.getTracks().forEach((track) => { track.stop() })
      void context.close()
    },
  }
}
