/**
 * Binds capture, the socket, and playback into one conversational turn.
 *
 * Audio frames arrive roughly ten times a second and never touch React state:
 * re-rendering at that rate would be wasteful and would not change the UI.
 * Only conversational events -- transcript, reply, expression -- are state.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { BargeInDetector, frameLevel } from './audio/barge-in'
import { startCapture, type Capture } from './audio/capture'
import { PcmPlayer, SILENT_FEATURES, type AudioFeatures } from './audio/playback'
import { startCamera, type Camera } from './camera'
import { decodePcm, DEFAULT_SAMPLE_RATE } from './protocol'
import { openSession, type Session } from './session'

export type Status = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error'

/** Long enough for the tail of her goodbye to finish playing. */
const FAREWELL_GRACE_MS = 1200

export interface Conversation {
  status: Status
  /** True once she has finished speaking the current reply. */
  replySpoken: boolean
  /** The camera stream, for a self-view, or null when the camera is off. */
  cameraStream: MediaStream | null
  cameraOn: boolean
  toggleCamera: () => void
  /** Current playback loudness, read per animation frame rather than as state. */
  loudness: () => number
  /** Returns the current spectral shape of her voice. */
  features: () => AudioFeatures
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
  const [replySpoken, setReplySpoken] = useState(false)

  const captureRef = useRef<Capture | null>(null)
  const sessionRef = useRef<Session | null>(null)
  const playerRef = useRef<PcmPlayer | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const bargeInRef = useRef(new BargeInDetector())
  const cameraRef = useRef<Camera | null>(null)
  const pendingFrame = useRef(false)
  const startingRef = useRef(false)
  const generationRef = useRef(0)
  const spokenRef = useRef(false)
  const frameSentRef = useRef(false)
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null)

  const teardown = useCallback(() => {
    generationRef.current += 1
    startingRef.current = false
    spokenRef.current = false
    captureRef.current?.stop()
    captureRef.current = null
    sessionRef.current?.close()
    sessionRef.current = null
    playerRef.current?.stop()
    playerRef.current = null
    cameraRef.current?.stop()
    cameraRef.current = null
    setCameraStream(null)
    // Browsers cap concurrent AudioContexts, so an unclosed one per turn
    // eventually refuses to start.
    void contextRef.current?.close()
    contextRef.current = null
  }, [])

  // StrictMode double-invokes effects, so teardown must be idempotent.
  useEffect(() => teardown, [teardown])

  const start = useCallback(() => {
    // Guards the whole async start, not just the resolved capture: the refs
    // stay null until getUserMedia resolves, so a second click would otherwise
    // open a second microphone that nothing can stop.
    if (startingRef.current) return
    startingRef.current = true
    const generation = ++generationRef.current
    setTranscript('')
    setReply('')
    setDetail('')
    setStatus('listening')

    // AudioContext must be created from the user gesture that called start().
    // The context is created now, from the user gesture; the player waits for
    // the server to announce the rate its audio actually uses.
    const context = new AudioContext()
    contextRef.current = context
    let player: PcmPlayer | null = null

    bargeInRef.current.reset()
    const session = openSession(characterId, {
      onMessage: (message) => {
        switch (message.type) {
          case 'transcript':
            setTranscript(message.text)
            setReplySpoken(false)
            // A new turn: whatever was cut off before is finished with, and
            // the next utterance gets a fresh still.
            bargeInRef.current.reset()
            frameSentRef.current = false
            setStatus('thinking')
            break
          case 'reply':
            setReply(message.text)
            // A new reply is unspoken until her audio for it has played.
            setReplySpoken(false)
            break
          case 'expression':
            setGesture(message.gesture)
            setEmotion(message.emotion)
            break
          case 'ready':
            player = new PcmPlayer(context, message.sample_rate)
            playerRef.current = player
            break
          case 'audio':
            spokenRef.current = true
            setStatus('speaking')
            if (!player) {
              player = new PcmPlayer(context, DEFAULT_SAMPLE_RATE)
              playerRef.current = player
            }
            player.enqueue(decodePcm(message.pcm))
            break
          case 'interrupted':
            // She stopped because we spoke over her; go straight back to
            // listening rather than reporting an error. Whatever she managed
            // to say is now on the record.
            playerRef.current?.stop()
            spokenRef.current = false
            setReplySpoken(true)
            setStatus('listening')
            break
          case 'farewell':
            // She has finished saying goodbye; let the last audio drain, then
            // close the way a call ends rather than cutting her off.
            window.setTimeout(() => {
              teardown()
              setStatus('idle')
            }, FAREWELL_GRACE_MS)
            break
          case 'error':
            setDetail(message.detail)
            teardown()
            setStatus('error')
            break
          case 'done':
            setReplySpoken(true)
            teardown()
            setStatus('idle')
            break
        }
      },
      onError: (message) => {
        setDetail(message)
        teardown()
        setStatus('error')
      },
      onClose: (event) => {
        // A clean close is the end of the conversation; anything else is a
        // connection that died under us and must be surfaced.
        if (!event.wasClean) setDetail('Connection lost.')
        teardown()
        setStatus(event.wasClean ? 'idle' : 'error')
      },
    })
    sessionRef.current = session

    const stale = () => generationRef.current !== generation

    startCapture((frame) => {
      session.sendAudio(frame)
      // One still per utterance. Ungated this ran on every audio frame, which
      // is ten JPEG uploads a second and continuous vision-token spend.
      if (cameraRef.current && !pendingFrame.current && !frameSentRef.current) {
        frameSentRef.current = true
        pendingFrame.current = true
        void cameraRef.current
          .grab()
          .then((frame) => (frame ? session.sendFrame(frame) : undefined))
          .finally(() => { pendingFrame.current = false })
      }

      // Only while she is actually speaking. Ungated, the threshold collapses
      // to the noise floor between replies and every ordinary utterance would
      // fire an interrupt.
      const player = playerRef.current
      if (spokenRef.current && player) {
        const speaking = player.currentLoudness()
        if (bargeInRef.current.observe(frameLevel(frame), speaking)) {
          spokenRef.current = false
          bargeInRef.current.reset()
          player.stop()
          session.interrupt()
          setStatus('listening')
        }
      }
    })
      .then((capture) => {
        if (stale()) {
          capture.stop()
          return
        }
        captureRef.current = capture
      })
      .catch((error: unknown) => {
        setDetail(error instanceof Error ? error.message : 'microphone unavailable')
        teardown()
        setStatus('error')
      })
      .finally(() => { startingRef.current = false })
  }, [characterId, teardown])

  const toggleCamera = useCallback(() => {
    if (cameraRef.current) {
      cameraRef.current.stop()
      cameraRef.current = null
      setCameraStream(null)
      return
    }
    startCamera()
      .then((camera) => {
        cameraRef.current = camera
        setCameraStream(camera.stream)
      })
      .catch(() => { setDetail('Could not open the camera.') })
  }, [])

  const stop = useCallback(() => {
    // There is no end of turn to signal in a live conversation: the button
    // ends the whole exchange, so everything is released and she falls silent.
    teardown()
    setStatus('idle')
  }, [teardown])

  // A function rather than a value: loudness changes every frame, and putting
  // it in state would re-render the whole tree 60 times a second.
  const loudness = useCallback(() => playerRef.current?.currentLoudness() ?? 0, [])

  // The player knows when its own queue has drained. Loudness cannot tell us:
  // audio is scheduled ahead of real time, so it is silent before the first
  // chunk sounds and again between sentences.
  useEffect(() => {
    if (status !== 'speaking') return
    const timer = window.setInterval(() => {
      if (playerRef.current?.isFinished() === true) setReplySpoken(true)
    }, 120)
    return () => { window.clearInterval(timer) }
  }, [status])

  // Reused between frames so the render loop allocates nothing.
  const featureScratch = useRef<AudioFeatures>({ ...SILENT_FEATURES })
  const features = useCallback(
    () =>
      playerRef.current?.readFeatures(featureScratch.current) ??
      Object.assign(featureScratch.current, SILENT_FEATURES),
    [],
  )

  return {
    status,
    transcript,
    reply,
    gesture,
    emotion,
    detail,
    loudness,
    features,
    replySpoken,
    cameraStream,
    cameraOn: cameraStream !== null,
    toggleCamera,
    start,
    stop,
  }
}
