/**
 * The uplink.
 *
 * Audio dropped here is invisible at both ends: the words are never
 * transcribed, and the gap reads to the recogniser as the speaker having
 * stopped talking. So the threshold for discarding it matters.
 */

import { describe, expect, it, vi } from 'vitest'

import { openSession } from './session'

class FakeSocket {
  static OPEN = 1
  readyState = 1
  bufferedAmount = 0
  sent: string[] = []
  send(payload: string): void { this.sent.push(payload) }
  close = vi.fn()
  addEventListener = vi.fn()
}

function withSocket(): { socket: FakeSocket; session: ReturnType<typeof openSession> } {
  const socket = new FakeSocket()
  vi.stubGlobal('WebSocket', Object.assign(function () { return socket }, { OPEN: 1, CONNECTING: 0 }))
  const session = openSession('bundled/seed', { onMessage: vi.fn() })
  return { socket, session }
}

describe('sending captured audio', () => {
  it('keeps sending through a stall of a few seconds', () => {
    // 100ms of speech is about 4.3KB on the wire. A brief hiccup on a slow
    // uplink easily backs up a second or two of it, and dropping frames then
    // tears a hole in the middle of a sentence.
    const { socket, session } = withSocket()
    socket.bufferedAmount = 200_000 // ~4.5s of speech queued

    session.sendAudio(new Int16Array(1600))

    expect(socket.sent).toHaveLength(1)
  })

  it('still refuses to queue without bound when the connection is broken', () => {
    const { socket, session } = withSocket()
    socket.bufferedAmount = 2_000_000

    session.sendAudio(new Int16Array(1600))

    expect(socket.sent).toHaveLength(0)
  })
})
