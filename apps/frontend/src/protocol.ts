/**
 * The wire protocol, mirroring the backend's typed messages.
 *
 * Messages arriving over the socket are untrusted input, so they are narrowed
 * by a parser rather than cast into shape.
 */

export interface TranscriptMessage {
  type: 'transcript'
  text: string
}

export interface ReplyMessage {
  type: 'reply'
  text: string
}

export interface AudioMessage {
  type: 'audio'
  pcm: string
}

export interface ExpressionMessage {
  type: 'expression'
  gesture: string
  emotion: string
}

export interface ErrorMessage {
  type: 'error'
  detail: string
}

export interface DoneMessage {
  type: 'done'
}

export type ServerMessage =
  | TranscriptMessage
  | ReplyMessage
  | AudioMessage
  | ExpressionMessage
  | ErrorMessage
  | DoneMessage

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Narrow an untrusted payload to a ServerMessage, or null if it is not one. */
export function parseServerMessage(raw: unknown): ServerMessage | null {
  if (!isRecord(raw)) return null

  switch (raw['type']) {
    case 'transcript':
    case 'reply':
      return typeof raw['text'] === 'string'
        ? { type: raw['type'], text: raw['text'] }
        : null
    case 'audio':
      return typeof raw['pcm'] === 'string' ? { type: 'audio', pcm: raw['pcm'] } : null
    case 'expression':
      return typeof raw['gesture'] === 'string' && typeof raw['emotion'] === 'string'
        ? { type: 'expression', gesture: raw['gesture'], emotion: raw['emotion'] }
        : null
    case 'error':
      return typeof raw['detail'] === 'string' ? { type: 'error', detail: raw['detail'] } : null
    case 'done':
      return { type: 'done' }
    default:
      return null
  }
}

/** Decode a base64 audio payload into 16-bit PCM samples. */
export function decodePcm(base64: string): Int16Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2))
}
