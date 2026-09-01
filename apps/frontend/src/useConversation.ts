/**
 * Binds capture, the socket, and playback into one conversational turn.
 *
 * Audio frames arrive roughly ten times a second and never touch React state:
 * re-rendering at that rate would be wasteful and would not change the UI.
 * Only conversational events -- transcript, reply, expression -- are state.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { startCapture, type Capture } from './audio/capture'
import { PcmPlayer } from './audio/playback'
import { decodePcm } from './protocol'
import { openSession, type Session } from './session'

export type Status = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error'

export interface Conversation {
  status: Status
  /** Current playback loudness, read per animation frame rather than as state. */
  loudness: () => number
  transcript: string
  reply: string
  gesture: string
  emotion: string
  detail: string
  start: () => void
  stop: () => void
}

export function useConversation(characterId: string): Conversation {
  const [status, setStatus] = useState<Status>('idle')
  const [transcript, setTranscript] = useState('')
  const [reply, setReply] = useState('')
  const [gesture, setGesture] = useState('idle')
  const [emotion, setEmotion] = useState('neutral')
  const [detail, setDetail] = useState('')

  const captureRef = useRef<Capture | null>(null)
  const sessionRef = useRef<Session | null>(null)
  const playerRef = useRef<PcmPlayer | null>(null)

  const teardown = useCallback(() => {
    captureRef.current?.stop()
    captureRef.current = null
    sessionRef.current?.close()
    sessionRef.current = null
    playerRef.current?.stop()
    playerRef.current = null
  }, [])

  // StrictMode double-invokes effects, so teardown must be idempotent.
  useEffect(() => teardown, [teardown])

  const start = useCallback(() => {
    if (captureRef.current !== null) return
    setTranscript('')
    setReply('')
    setDetail('')
    setStatus('listening')

    // AudioContext must be created from the user gesture that called start().
    const player = new PcmPlayer(new AudioContext())
    playerRef.current = player

    const session = openSession(characterId, {
      onMessage: (message) => {
        switch (message.type) {
          case 'transcript':
            setTranscript(message.text)
            setStatus('thinking')
            break
          case 'reply':
            setReply(message.text)
            break
          case 'expression':
            setGesture(message.gesture)
            setEmotion(message.emotion)
            break
          case 'audio':
            setStatus('speaking')
            player.enqueue(decodePcm(message.pcm))
            break
          case 'error':
            setDetail(message.detail)
            setStatus('error')
            break
          case 'done':
            setStatus('idle')
            break
        }
      },
      onError: (message) => {
        setDetail(message)
        setStatus('error')
      },
    })
    sessionRef.current = session

    startCapture((frame) => { session.sendAudio(frame) })
      .then((capture) => { captureRef.current = capture })
      .catch((error: unknown) => {
        setDetail(error instanceof Error ? error.message : 'microphone unavailable')
        setStatus('error')
      })
  }, [characterId])

  const stop = useCallback(() => {
    captureRef.current?.stop()
    captureRef.current = null
    sessionRef.current?.stopSpeaking()
    setStatus((current) => (current === 'listening' ? 'thinking' : current))
  }, [])

  // A function rather than a value: loudness changes every frame, and putting
  // it in state would re-render the whole tree 60 times a second.
  const loudness = useCallback(() => playerRef.current?.currentLoudness() ?? 0, [])

  return { status, transcript, reply, gesture, emotion, detail, loudness, start, stop }
}
