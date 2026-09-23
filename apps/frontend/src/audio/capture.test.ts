import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { startCapture } from './capture'

const recordMicrophone = vi.hoisted(() => vi.fn())
vi.mock('../diagnostics', () => ({ recordMicrophone }))
const track = { stop: vi.fn(), label: 'Test headset', getSettings: () => ({
  echoCancellation: true, noiseSuppression: true, autoGainControl: false,
}) }
const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
const source = { connect: vi.fn(), disconnect: vi.fn() }
const highpass = { type: '', frequency: { value: 0 }, Q: { value: 0 },
  connect: vi.fn(), disconnect: vi.fn() }
const context = { sampleRate: 16000, resume: vi.fn(async () => {}),
  close: vi.fn(async () => {}), audioWorklet: { addModule: vi.fn(async () => {}) },
  createMediaStreamSource: () => source, createBiquadFilter: () => highpass }
const getUserMedia = vi.fn(() => Promise.resolve(stream))
beforeEach(() => {
  vi.clearAllMocks()
  context.sampleRate = 16000
  context.audioWorklet.addModule.mockResolvedValue()
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
  vi.stubGlobal('AudioContext', function () { return context })
  vi.stubGlobal('AudioWorkletNode', function () {
    return { port: { onmessage: null }, disconnect: vi.fn() }
  })
})
afterEach(() => { vi.unstubAllGlobals() })
it('preserves echo cancellation and noise suppression independently of automatic gain', async () => {
  const capture = await startCapture(vi.fn(), false)
  expect(getUserMedia).toHaveBeenCalledWith({ audio: {
    channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false,
  } })
  expect(context.resume).toHaveBeenCalled()
  expect(recordMicrophone).toHaveBeenCalledWith({ label: 'Test headset',
    echoCancellation: true, noiseSuppression: true, autoGainControl: false, captureSampleRate: 16000 })
  capture.stop()
  capture.stop()
  expect(track.stop).toHaveBeenCalledTimes(1)
})
it('releases capture when initialization fails', async () => {
  context.audioWorklet.addModule.mockRejectedValueOnce(new Error('worklet failed'))
  await expect(startCapture(vi.fn())).rejects.toThrow('worklet failed')
  expect(track.stop).toHaveBeenCalledOnce()
  expect(context.close).toHaveBeenCalledOnce()
})
it('refuses to mislabel audio when the browser ignores the requested sample rate', async () => {
  context.sampleRate = 48000
  await expect(startCapture(vi.fn())).rejects.toThrow('16 kHz')
  expect(track.stop).toHaveBeenCalledOnce()
})

it('filters rumble before delivering continuous audio and releases the filter', async () => {
  let port: { onmessage: ((event: { data: Int16Array }) => void) | null } | undefined
  const worklet = { port: { onmessage: null }, disconnect: vi.fn() }
  vi.stubGlobal('AudioWorkletNode', function () {
    port = worklet.port
    return worklet
  })
  const onFrame = vi.fn()
  const capture = await startCapture(onFrame, false)
  expect(source.connect).toHaveBeenCalledWith(highpass)
  expect(highpass.connect).toHaveBeenCalledWith(worklet)
  expect(highpass.type).toBe('highpass')
  expect(highpass.frequency.value).toBe(80)
  expect(highpass.Q.value).toBeCloseTo(-3.0103)
  const quietFrame = new Int16Array([0, 1, -1])
  port?.onmessage?.({ data: quietFrame })
  expect(onFrame).toHaveBeenCalledWith(quietFrame)
  capture.stop()
  capture.stop()
  expect(highpass.disconnect).toHaveBeenCalledOnce()
  expect(port?.onmessage).toBeNull()
})

it('releases the filter and microphone if worklet construction fails', async () => {
  vi.stubGlobal('AudioWorkletNode', function () { throw new Error('construction failed') })
  await expect(startCapture(vi.fn())).rejects.toThrow('construction failed')
  expect(highpass.disconnect).toHaveBeenCalledOnce()
  expect(track.stop).toHaveBeenCalledOnce()
  expect(context.close).toHaveBeenCalledOnce()
})
