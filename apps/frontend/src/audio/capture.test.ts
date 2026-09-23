import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { startCapture } from './capture'

const recordMicrophone = vi.hoisted(() => vi.fn())
vi.mock('../diagnostics', () => ({ recordMicrophone }))
const track = { stop: vi.fn(), label: 'Test headset', getSettings: () => ({
  echoCancellation: true, noiseSuppression: true, autoGainControl: false,
}) }
const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
const source = { connect: vi.fn(), disconnect: vi.fn() }
const context = { sampleRate: 16000, resume: vi.fn(async () => {}),
  close: vi.fn(async () => {}), audioWorklet: { addModule: vi.fn(async () => {}) },
  createMediaStreamSource: () => source }
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
