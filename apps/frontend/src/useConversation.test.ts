/**
 * Turn lifecycle.
 *
 * These cover the ways a turn can end, because "thinking" is the state the UI
 * gets stuck in when one of them is missed.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ServerMessage } from './protocol'
import type { SessionHandlers } from './session'
import { useConversation } from './useConversation'

let deliver: (message: ServerMessage) => void = () => {}

vi.mock('./session', () => ({
  openSession: (_id: string, handlers: SessionHandlers) => {
    deliver = handlers.onMessage
    return {
      sendAudio: vi.fn(), sendFrame: vi.fn(), stopSpeaking: vi.fn(),
      interrupt: vi.fn(), close: vi.fn(),
    }
  },
}))

vi.mock('./audio/capture', () => ({
  startCapture: () => Promise.resolve({ stop: vi.fn(), context: { close: vi.fn() } }),
}))

// jsdom has no Web Audio; the hook only needs a context it can later close.
class FakeAudioContext {
  currentTime = 0
  sampleRate = 24_000
  destination = {}
  close = vi.fn(() => Promise.resolve())
  resume = vi.fn(() => Promise.resolve())
  createBuffer(_channels: number, length: number) {
    return { getChannelData: () => new Float32Array(length) }
  }
  createBufferSource() {
    return {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null,
    }
  }
  createAnalyser() {
    return {
      fftSize: 0,
      frequencyBinCount: 32,
      connect: vi.fn(),
      disconnect: vi.fn(),
      getByteFrequencyData: vi.fn(),
      getByteTimeDomainData: vi.fn(),
    }
  }
  createGain() {
    return { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() }
  }
}
vi.stubGlobal('AudioContext', FakeAudioContext)

afterEach(() => { vi.useRealTimers() })

async function started() {
  const hook = renderHook(() => useConversation('bundled/seed'))
  // start() kicks off async capture; flush it before asserting.
  await act(async () => {
    hook.result.current.start()
    await Promise.resolve()
  })
  return hook
}

describe('ending a turn', () => {
  it('does not sit on "thinking" when the reply carries no audio', async () => {
    // Muted voice, a synthesis failure, an empty reply: the turn is still over
    // and the UI must not wait on a sound that is never coming.
    const { result } = await started()

    act(() => { deliver({ type: 'transcript', text: 'Hello' }) })
    expect(result.current.status).toBe('thinking')

    act(() => { deliver({ type: 'reply', text: 'Hello there.' }) })

    await waitFor(() => { expect(result.current.status).toBe('listening') })
  })

  it('gives up rather than thinking forever when nothing comes back', async () => {
    vi.useFakeTimers()
    const { result } = await started()

    act(() => { deliver({ type: 'transcript', text: 'Hello' }) })
    expect(result.current.status).toBe('thinking')

    act(() => { vi.advanceTimersByTime(31_000) })

    expect(result.current.status).toBe('error')
  })
})

