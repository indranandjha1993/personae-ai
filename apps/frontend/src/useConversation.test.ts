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
  static latest: FakeAudioContext
  constructor() { FakeAudioContext.latest = this }
  sources: { onended: (() => void) | null; stop: ReturnType<typeof vi.fn> }[] = []
  currentTime = 0
  sampleRate = 24_000
  destination = {}
  close = vi.fn(() => Promise.resolve())
  resume = vi.fn(() => Promise.resolve())
  createBuffer(_channels: number, length: number) {
    return { duration: length / this.sampleRate, getChannelData: () => new Float32Array(length) }
  }
  createBufferSource() {
    const source = {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
    }
    this.sources.push(source)
    return source
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
    deliver({ type: 'ready', sample_rate: 24000, channels: 1 })
  })
  return hook
}

describe('a failed turn', () => {
  it('reports the failure and keeps listening', async () => {
    // A provider refusing one turn is not the conversation ending; tearing
    // the session down turned every transient into a dead call.
    const { result } = await started()

    act(() => { deliver({ type: 'transcript', text: 'Hello' }) })
    act(() => { deliver({ type: 'error', detail: 'the voice failed' }) })

    expect(result.current.status).toBe('listening')
    expect(result.current.detail).toBe('the voice failed')

    act(() => { deliver({ type: 'transcript', text: 'Again' }) })
    expect(result.current.detail).toBe('')
  })
})

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

    act(() => { vi.advanceTimersByTime(46_000) })

    expect(result.current.status).toBe('error')
  })

  it('keeps waiting while the reply is visibly arriving', async () => {
    // A slow model that has already sent its first sentence is not a dead
    // one; the clock runs from the last sign of life, not from the question.
    vi.useFakeTimers()
    const { result } = await started()

    act(() => { deliver({ type: 'transcript', text: 'Hello' }) })
    act(() => { vi.advanceTimersByTime(40_000) })
    act(() => { deliver({ type: 'expression', gesture: 'idle', emotion: 'neutral' }) })
    act(() => { vi.advanceTimersByTime(40_000) })

    expect(result.current.status).toBe('thinking')

    act(() => { vi.advanceTimersByTime(10_000) })
    expect(result.current.status).toBe('error')
  })
})


describe('session isolation', () => {
  it('ignores old callbacks after ending and restarting', async () => {
    const { result } = await started()
    const oldDeliver = deliver
    act(() => { result.current.stop() })
    await act(async () => { result.current.start(); await Promise.resolve() })
    act(() => { deliver({ type: 'transcript', text: 'New session' }) })
    act(() => { oldDeliver({ type: 'transcript', text: 'Stale session' }) })
    expect(result.current.transcript).toBe('New session')
  })
})


it('waits for server readiness before claiming to listen', async () => {
  const { result } = renderHook(() => useConversation('bundled/seed'))
  await act(async () => { result.current.start(); await Promise.resolve() })
  expect(result.current.status).toBe('connecting')
  act(() => { deliver({ type: 'ready', sample_rate: 24000, channels: 1 }) })
  expect(result.current.status).toBe('listening')
})

it('times out a connection that never becomes ready', async () => {
  vi.useFakeTimers()
  const { result } = renderHook(() => useConversation('bundled/seed'))
  await act(async () => { result.current.start(); await Promise.resolve() })
  act(() => { vi.advanceTimersByTime(21_000) })
  expect(result.current.status).toBe('error')
  expect(result.current.detail).toContain('Connection timed out')
})

it('does not remain speaking forever when the audio clock stalls', async () => {
  vi.useFakeTimers()
  const { result } = await started()
  act(() => {
    deliver({ type: 'transcript', text: 'Hello' })
    deliver({ type: 'audio', samples: new Int16Array(2400) })
  })
  act(() => { vi.advanceTimersByTime(11_000) })
  expect(result.current.status).toBe('error')
  expect(result.current.detail).toContain('Audio playback stopped')
})


it('waits for unfinished generation after queued audio drains, then times out', async () => {
  vi.useFakeTimers()
  const { result } = await started()
  act(() => {
    deliver({ type: 'transcript', text: 'Hello' })
    deliver({ type: 'audio', samples: new Int16Array(2400) })
  })
  act(() => {
    FakeAudioContext.latest.currentTime = 1
    FakeAudioContext.latest.sources.forEach((source) => source.onended?.())
    vi.advanceTimersByTime(200)
  })
  expect(result.current.status).toBe('thinking')
  act(() => { vi.advanceTimersByTime(46_000) })
  expect(result.current.status).toBe('error')
})

it('stops old queued audio when the next transcript arrives', async () => {
  const { result } = await started()
  act(() => { deliver({ type: 'audio', samples: new Int16Array(2400) }) })
  const source = FakeAudioContext.latest.sources[0]
  if (!source) throw new Error('Expected queued audio')
  act(() => { deliver({ type: 'transcript', text: 'New turn' }) })
  expect(source.stop).toHaveBeenCalled()
  expect(result.current.status).toBe('thinking')
})
