/**
 * The conversational WebSocket session.
 *
 * Deliberately framework-agnostic so it can be tested without rendering a
 * component; React binds to it through a hook.
 */

import { parseServerMessage, type ServerMessage } from './protocol'

export interface SessionHandlers {
  onMessage: (message: ServerMessage) => void
  onClose?: (event: CloseEvent) => void
  onError?: (detail: string) => void
}

export interface Session {
  sendAudio: (frame: Int16Array) => void
  stopSpeaking: () => void
  close: () => void
}

function toBase64(frame: Int16Array): string {
  const bytes = new Uint8Array(frame.buffer, frame.byteOffset, frame.byteLength)
  let binary = ''
  // Chunked to stay well clear of the argument limit on large frames.
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  }
  return btoa(binary)
}

export function openSession(characterId: string, handlers: SessionHandlers): Session {
  const url = new URL(`/ws/session/${characterId}`, window.location.href)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  const socket = new WebSocket(url)

  socket.onmessage = (event: MessageEvent<string>) => {
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

  const sendWhenOpen = (payload: object) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload))
  }

  return {
    sendAudio: (frame) => { sendWhenOpen({ type: 'audio', pcm: toBase64(frame) }) },
    stopSpeaking: () => { sendWhenOpen({ type: 'stop' }) },
    close: () => { socket.close() },
  }
}
