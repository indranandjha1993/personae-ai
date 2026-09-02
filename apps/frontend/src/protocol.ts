/**
 * The wire protocol, mirroring the backend's typed messages.
 *
 * Messages arriving over the socket are untrusted input, so they are narrowed
 * by a parser rather than cast into shape.
 */

export interface ReadyMessage {
  type: 'ready'
  sample_rate: number
  channels: number
}

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

export interface InterruptedMessage {
  type: 'interrupted'
}

export interface ErrorMessage {
  type: 'error'
  detail: string
}

export interface DoneMessage {
  type: 'done'
}

export type ServerMessage =
  | ReadyMessage
  | TranscriptMessage
  | ReplyMessage
  | AudioMessage
  | ExpressionMessage
  | InterruptedMessage
  | ErrorMessage
  | DoneMessage

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** Narrow an untrusted payload to a ServerMessage, or null if it is not one. */
export function parseServerMessage(raw: unknown): ServerMessage | null {
  if (!isRecord(raw)) return null

  switch (raw['type']) {
    case 'ready':
      return typeof raw['sample_rate'] === 'number' && typeof raw['channels'] === 'number'
        ? { type: 'ready', sample_rate: raw['sample_rate'], channels: raw['channels'] }
        : null
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
    case 'interrupted':
      return { type: 'interrupted' }
    case 'done':
      return { type: 'done' }
    default:
      return null
  }
}

/**
 * Fallback sample rate, used only if the server never announces one.
 *
 * The server sends a `ready` message with the real rate on connect; playing the
 * samples at any other rate shifts pitch and speed.
 */
export const DEFAULT_SAMPLE_RATE = 24_000

/** Decode a base64 audio payload into 16-bit PCM samples. */
export function decodePcm(base64: string): Int16Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2))
}
