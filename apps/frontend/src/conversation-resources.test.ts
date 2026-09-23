import { expect, it, vi } from 'vitest'
import { ConversationResources } from './conversation-resources'
import type { PcmPlayer } from './audio/playback'
import type { Session } from './conversation-socket'

it('invalidates late startup callbacks and permits a fresh attempt after release', () => {
  const resources = new ConversationResources()
  const first = resources.begin()
  if (first === null) throw new Error('Expected a startup token')
  expect(resources.begin()).toBeNull()
  expect(resources.isCurrent(first)).toBe(true)
  resources.release()
  const next = resources.begin()
  if (next === null) throw new Error('Expected a new startup token')
  expect(resources.isCurrent(first)).toBe(false)
  expect(resources.isCurrent(next)).toBe(true)
})

it('releases every resource once even if device cleanup throws', async () => {
  const resources = new ConversationResources()
  const generation = resources.begin()
  if (generation === null) throw new Error('Expected a startup token')
  const stopCapture = vi.fn(() => { throw new Error('device disappeared') })
  const closeSocket = vi.fn(() => { expect(resources.isCurrent(generation)).toBe(false) })
  const stopPlayback = vi.fn()
  const closeAudio = vi.fn(() => Promise.reject(new Error('already closed')))
  resources.capture = { stop: stopCapture, sampleRate: 16000 }
  resources.session = { close: closeSocket } as unknown as Session
  resources.player = { stop: stopPlayback } as unknown as PcmPlayer
  resources.context = { close: closeAudio } as unknown as AudioContext
  resources.release()
  resources.release()
  await Promise.resolve()
  for (const cleanup of [stopCapture, closeSocket, stopPlayback, closeAudio]) {
    expect(cleanup).toHaveBeenCalledTimes(1)
  }
  expect(resources.capture).toBeNull()
  expect(resources.session).toBeNull()
  expect(resources.player).toBeNull()
  expect(resources.context).toBeNull()
})
