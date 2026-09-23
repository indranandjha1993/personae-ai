/**
 * Microphone capture via AudioWorklet.
 *
 * ScriptProcessorNode is deprecated and runs on the main thread, so capture
 * happens in a worklet on the audio thread instead. A dedicated 16 kHz context
 * is used because that is what the speech recogniser expects; resampling here
 * is cheaper and more predictable than doing it downstream.
 */

import { recordMicrophone } from '../diagnostics'

const CAPTURE_SAMPLE_RATE = 16_000
// Remove low-frequency rumble while retaining the speech band.
const RUMBLE_CUTOFF_HZ = 80
const WORKLET_URL = '/pcm-capture.worklet.js'

export interface Capture {
  stop: () => void
  /** The rate capture actually runs at, which may not be the one requested. */
  sampleRate: number
}

/**
 * Start capturing, invoking `onFrame` with 80 ms of 16-bit PCM at a time.
 *
 * Must be called from a user gesture: browsers refuse to start an AudioContext
 * otherwise.
 */
export async function startCapture(
  onFrame: (frame: Int16Array<ArrayBuffer>) => void,
  autoGainControl = true,
): Promise<Capture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      // Room noise reaching the recogniser does two things: it costs words,
      // and it keeps the turn detector unsure the speaker has finished, so
      // the reply waits on a timeout. A laptop microphone in a real room
      // needs this on.
      noiseSuppression: true,
      // Lifts a quiet or distant speaker rather than leaving the recogniser
      // to work from what little reaches the microphone.
      autoGainControl,
    },
  })

  let context: AudioContext | undefined
  let source: MediaStreamAudioSourceNode | undefined
  let highpass: BiquadFilterNode | undefined
  let worklet: AudioWorkletNode | undefined
  let stopped = false
  const stop = () => {
    if (stopped) return
    stopped = true
    if (worklet) worklet.port.onmessage = null
    source?.disconnect()
    highpass?.disconnect()
    worklet?.disconnect()
    stream.getTracks().forEach((track) => { track.stop() })
    if (context) void context.close().catch(() => {})
  }
  try {
    context = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE })
    // Never tell STT that a different-rate stream is 16 kHz.
    if (context.sampleRate !== CAPTURE_SAMPLE_RATE) {
      throw new Error('This browser could not start a 16 kHz microphone stream.')
    }
    await context.resume()
    await context.audioWorklet.addModule(WORKLET_URL)
    source = context.createMediaStreamSource(stream)
    highpass = context.createBiquadFilter()
    highpass.type = 'highpass'
    highpass.frequency.value = RUMBLE_CUTOFF_HZ
    // Web Audio expresses highpass Q in dB: -3.01 dB gives a flat
    // Butterworth response, without amplifying noise near the cutoff.
    highpass.Q.value = -3.0103
    worklet = new AudioWorkletNode(context, 'pcm-capture')
    worklet.port.onmessage = (event: MessageEvent<Int16Array<ArrayBuffer>>) => {
      if (!stopped) onFrame(event.data)
    }
    source.connect(highpass)
    highpass.connect(worklet)
    const track = stream.getAudioTracks()[0]
    const settings = track?.getSettings()
    recordMicrophone({
      label: track?.label ?? 'Unknown microphone',
      echoCancellation: settings?.echoCancellation ?? null,
      noiseSuppression: settings?.noiseSuppression ?? null,
      autoGainControl: settings?.autoGainControl ?? null,
      captureSampleRate: context.sampleRate,
    })
    return { sampleRate: context.sampleRate, stop }
  } catch (error) {
    stop()
    throw error
  }
}
