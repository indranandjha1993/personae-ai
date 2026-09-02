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

/** Give up waiting for a goodbye to finish after this. */
const FAREWELL_MAX_WAIT_MS = 15_000

/** How long she may think before we assume the reply is not coming. */
const THINKING_TIMEOUT_MS = 30_000

export interface Conversation {
  status: Status
  /** What she has said so far this turn, growing sentence by sentence. */
  spokenSoFar: string
  /** True once the whole reply has been delivered and heard. */
  turnFinished: boolean
  /** Increments per reply, so the caption animates once rather than per sentence. */
  turnId: number
  /** How loud the microphone is hearing the listener, 0..1. */
  inputLevel: () => number
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
  const [spokenSoFar, setSpokenSoFar] = useState('')
  const [turnFinished, setTurnFinished] = useState(false)
  const [playbackDone, setPlaybackDone] = useState(false)
  const [turnId, setTurnId] = useState(0)
  const inputLevelRef = useRef(0)
  const queued = useRef<{ text: string; playedBy: number | null }[]>([])
  const suppressing = useRef(false)

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
    //
    // It runs at the rate her voice is synthesised at. Left at the device
    // default, the browser resamples every buffer as it is scheduled, and on
    // the small chunks that arrive over a socket that resampling is audibly
    // rough. Matching the source rate means it never has to.
    //
    // The player is still told the rate the server announces, so a server
    // synthesising at something else stays correct -- it just costs the
    // resampling this avoids in the common case.
    const context = new AudioContext({ sampleRate: DEFAULT_SAMPLE_RATE })
    contextRef.current = context
    let player: PcmPlayer | null = null

    bargeInRef.current.reset()
    const session = openSession(characterId, {
      onMessage: (message) => {
        switch (message.type) {
          case 'hearing':
            // Provisional: the listener watching themselves be heard. It is
            // replaced by the next one and never acted on.
            setTranscript(message.text)
            break
          case 'transcript':
            suppressing.current = false
            setTranscript(message.text)
            // A new turn starts with nothing said yet.
            setReply('')
            setSpokenSoFar('')
            setTurnFinished(false)
            setPlaybackDone(false)
            queued.current = []
            setTurnId((previous) => previous + 1)
            // A new turn: whatever was cut off before is finished with, and
            // the next utterance gets a fresh still.
            bargeInRef.current.reset()
            frameSentRef.current = false
            setStatus('thinking')
            break
          case 'speaking':
            if (suppressing.current) break
            // Held until its audio has actually played. The socket delivers
            // far faster than real time, so revealing on arrival would put the
            // whole reply on screen while she is still on the first sentence.
            queued.current.push({ text: message.text, playedBy: null })
            break
          case 'reply':
            // Closes the turn. The full text supersedes what was accumulated,
            // so anything the splitter dropped is still shown.
            setReply(message.text)
            setTurnFinished(true)
            // A reply with no audio behind it -- muted voice, a TTS failure,
            // an empty synthesis -- still ends the turn. Without this the UI
            // waits on a sound that is never coming.
            if (queued.current.length === 0 && !spokenRef.current) {
              setPlaybackDone(true)
              setStatus('listening')
            }
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
            if (suppressing.current) break
            spokenRef.current = true
            setStatus('speaking')
            // The first chunk of a sentence fixes when that sentence ends.
            for (const pending of queued.current) {
              if (pending.playedBy === null) {
                pending.playedBy = (playerRef.current?.scheduledUntil ?? 0) + 0.001
                break
              }
            }
            if (!player) {
              player = new PcmPlayer(context, DEFAULT_SAMPLE_RATE)
              playerRef.current = player
            }
            player.enqueue(decodePcm(message.pcm))
            break
          case 'interrupted':
            suppressing.current = false
            // She stopped because we spoke over her; go straight back to
            // listening rather than reporting an error. Whatever she managed
            // to say is now on the record.
            playerRef.current?.stop()
            spokenRef.current = false
            setTurnFinished(true)
            setStatus('listening')
            break
          case 'farewell': {
            // Wait for the goodbye to actually finish. A fixed delay cut her
            // off mid-word, because the audio is queued long before it plays.
            const started = Date.now()
            const closing = window.setInterval(() => {
              const done = playerRef.current?.isFinished() ?? true
              if (done || Date.now() - started > FAREWELL_MAX_WAIT_MS) {
                window.clearInterval(closing)
                teardown()
                setStatus('idle')
              }
            }, 150)
            break
          }
          case 'error':
            setDetail(message.detail)
            teardown()
            setStatus('error')
            break
          case 'done':
            setTurnFinished(true)
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
      inputLevelRef.current = frameLevel(frame)
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
          // Messages already in flight would otherwise restart her audio and
          // add sentences to the caption that were never heard.
          suppressing.current = true
          queued.current = []
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
  const inputLevel = useCallback(() => inputLevelRef.current, [])

  // "Thinking" is never a resting state: if nothing comes back, say so rather
  // than leaving the user watching a label forever.
  useEffect(() => {
    if (status !== 'thinking') return
    const giveUp = window.setTimeout(() => {
      setDetail('She did not answer.')
      teardown()
      setStatus('error')
    }, THINKING_TIMEOUT_MS)
    return () => { window.clearTimeout(giveUp) }
  }, [status, teardown])

  // Caption and teardown both run on the player's clock rather than on message
  // arrival: audio is delivered far faster than it is heard, so anything keyed
  // to the socket shows the words seconds before she says them.
  useEffect(() => {
    if (status !== 'speaking') return
    const tick = window.setInterval(() => {
      const player = playerRef.current
      if (!player) return

      const heard = queued.current.filter(
        (pending) => pending.playedBy !== null && pending.playedBy <= player.now,
      )
      if (heard.length > 0) {
        queued.current = queued.current.filter((pending) => !heard.includes(pending))
        setSpokenSoFar((said) =>
          [said, ...heard.map((pending) => pending.text)].filter(Boolean).join(' '),
        )
      }
      if (player.isFinished() && queued.current.length === 0) setPlaybackDone(true)
    }, 100)
    return () => { window.clearInterval(tick) }
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
    spokenSoFar,
    turnFinished: turnFinished && playbackDone,
    turnId,
    inputLevel,
    cameraStream,
    cameraOn: cameraStream !== null,
    toggleCamera,
    start,
    stop,
  }
}
