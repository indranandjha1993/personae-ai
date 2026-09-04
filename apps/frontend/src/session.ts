/**
 * The conversational WebSocket session.
 *
 * Deliberately framework-agnostic so it can be tested without rendering a
 * component; React binds to it through a hook.
 */

import { audioFrom, parseServerMessage, type ServerMessage } from './protocol'

export interface SessionHandlers {
  onMessage: (message: ServerMessage) => void
  onClose?: (event: CloseEvent) => void
  onError?: (detail: string) => void
}

export interface Session {
  sendAudio: (frame: Int16Array<ArrayBuffer>) => void
  sendFrame: (jpeg: Blob) => Promise<void>
  stopSpeaking: () => void
  interrupt: () => void
  close: () => void
}

/** About a second of audio; beyond this the uplink is not keeping up. */
/**
 * How much unsent audio may pile up before frames start being discarded.
 *
 * A dropped frame is a hole punched in the middle of a sentence: the words in
 * it are never transcribed, and the silence it leaves can read to the
 * recogniser as the speaker having finished. 64KB is only about a second and a
 * half of speech, which a brief stall on a slow uplink passes easily, so this
 * is generous enough that only a genuinely broken connection reaches it.
 */
const MAX_BUFFERED_BYTES = 512_000

/** What may wait for the socket to open: JSON text, or a raw audio frame. */
type Outbound = string | Int16Array<ArrayBuffer>

export function openSession(characterId: string, handlers: SessionHandlers): Session {
  const url = new URL(`/ws/live/${characterId}`, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  const socket = new WebSocket(url)
  // Her voice comes back as raw frames; a Blob would need an async read.
  socket.binaryType = 'arraybuffer'

  socket.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
    if (event.data instanceof ArrayBuffer) {
      handlers.onMessage(audioFrom(event.data))
      return
    }
    let payload: unknown
    try {
      payload = JSON.parse(event.data)
    } catch {
      handlers.onError?.('server sent a malformed message')
      return
    }
    const message = parseServerMessage(payload)
    if (message === null) {
      handlers.onError?.('server sent an unrecognised message')
      return
    }
    handlers.onMessage(message)
  }

  socket.onclose = (event) => { handlers.onClose?.(event) }
  socket.onerror = () => { handlers.onError?.('connection failed') }

  // Roughly two seconds of audio in 80ms frames. Capture starts before the
  // handshake finishes, so without this the first word of the conversation
  // is lost.
  const MAX_PENDING = 25
  let pending: Outbound[] = []

  socket.addEventListener('open', () => {
    for (const payload of pending) socket.send(payload)
    pending = []
  })

  const sendWhenOpen = (payload: object | Int16Array<ArrayBuffer>) => {
    // Audio goes as it is; everything else is JSON.
    const encoded: Outbound = payload instanceof Int16Array ? payload : JSON.stringify(payload)
    if (socket.readyState === WebSocket.OPEN) {
      // Drop rather than queue without bound if the uplink has stalled. Not
      // reported as an error: a conversation that survives a hiccup is better
      // than one torn down over it, and the cap is high enough that reaching
      // it means the connection is already failing on its own.
      if (socket.bufferedAmount > MAX_BUFFERED_BYTES) return
      socket.send(encoded)
      return
    }
    if (socket.readyState === WebSocket.CONNECTING && pending.length < MAX_PENDING) {
      pending.push(encoded)
    }
  }

  return {
    sendAudio: (frame) => { sendWhenOpen(frame) },
    stopSpeaking: () => { sendWhenOpen({ type: 'stop' }) },
    interrupt: () => { sendWhenOpen({ type: 'interrupt' }) },
    sendFrame: async (jpeg) => {
      const bytes = new Uint8Array(await jpeg.arrayBuffer())
      let binary = ''
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
      }
      sendWhenOpen({ type: 'vision', jpeg: btoa(binary) })
    },
    close: () => { socket.close() },
  }
}
