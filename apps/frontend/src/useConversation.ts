/**
 * Binds capture, the socket, and playback into one conversational turn.
 *
 * Audio frames arrive roughly ten times a second and never touch React state:
 * re-rendering at that rate would be wasteful and would not change the UI.
 * Only conversational events -- transcript, reply, expression -- are state.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { SpeechTimeline, type MouthWeights } from './audio/speech-timeline'
import { recordMetric } from './diagnostics'

import { BargeInDetector, frameLevel } from './audio/barge-in'
import { startCapture, type Capture } from './audio/capture'
import { PcmPlayer, SILENT_FEATURES, type AudioFeatures } from './audio/playback'
import { startCamera, type Camera } from './camera'
import { DEFAULT_SAMPLE_RATE } from './protocol'
import { openSession, type Session } from './session'

export type Status = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'error'

/** Give up waiting for a goodbye to finish after this. */
const FAREWELL_MAX_WAIT_MS = 15_000

/**
 * How long she may go without any sign of progress before the reply is
 * assumed lost. Counted from the last message, not from the transcript: a
 * slow model that is visibly writing is not the same as one that has died.
 */
const THINKING_TIMEOUT_MS = 45_000

export interface Conversation {
  mouthCues: () => MouthWeights | null
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

export function useConversation(characterId: string, voiceId = 'default', allowVoiceInterruption = true, microphoneAutoVolume = true): Conversation {
  const speechTimeline = useRef(new SpeechTimeline())
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
  // When something last arrived while she was thinking; re-arms the give-up timer.
  const [progressAt, setProgressAt] = useState(0)
  const inputLevelRef = useRef(0)
  const queued = useRef<
    { text: string; playedBy: number | null; gesture?: string; emotion?: string }[]
  >([])
  const pendingExpression = useRef<{ gesture: string; emotion: string } | null>(null)
  const suppressing = useRef(false)

  const captureRef = useRef<Capture | null>(null)
  const sessionRef = useRef<Session | null>(null)
  const playerRef = useRef<PcmPlayer | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const bargeInRef = useRef(new BargeInDetector())
  const cameraRef = useRef<Camera | null>(null)
  const pendingFrame = useRef(false)
  const cameraGeneration = useRef(0)
  const cameraStarting = useRef(false)
  const farewellTimer = useRef<number | null>(null)
  const receivedReply = useRef(false)
  const awaitingReply = useRef(false)
  const startingRef = useRef(false)
  const generationRef = useRef(0)
  const spokenRef = useRef(false)
  const frameSentRef = useRef(false)
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null)

  const teardown = useCallback(() => {
    speechTimeline.current.clear()
    if (farewellTimer.current !== null) window.clearInterval(farewellTimer.current)
    farewellTimer.current = null
    cameraGeneration.current += 1
    cameraStarting.current = false
    queued.current = []
    pendingExpression.current = null
    pendingFrame.current = false
    frameSentRef.current = false
    suppressing.current = false
    inputLevelRef.current = 0
    generationRef.current += 1
    startingRef.current = false
    spokenRef.current = false
    awaitingReply.current = false
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
    if (startingRef.current || sessionRef.current) return
    startingRef.current = true
    const generation = ++generationRef.current
    const stale = () => generationRef.current !== generation
    receivedReply.current = false
    setTranscript('')
    setReply('')
    setDetail('')
    setSpokenSoFar('')
    setTurnFinished(false)
    setPlaybackDone(false)
    setProgressAt(Date.now())
    setStatus('connecting')

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
    let context: AudioContext
    try {
      context = new AudioContext({ sampleRate: DEFAULT_SAMPLE_RATE })
    } catch {
      startingRef.current = false
      setDetail('Audio is unavailable in this browser.')
      setStatus('error')
      return
    }
    contextRef.current = context
    let ready = false
    let captureReady = false
    let audioReady = false
    const markConnected = () => {
      if (!stale() && ready && captureReady && audioReady) setStatus('listening')
    }
    void context.resume().then(() => {
      audioReady = true
      markConnected()
    }).catch(() => {
      if (stale()) return
      setDetail('Audio could not start. Try starting the conversation again.')
      teardown()
      setStatus('error')
    })
    let player: PcmPlayer | null = null
    let audioOffset = 0
    let sampleRate = DEFAULT_SAMPLE_RATE
    let transcriptAt = 0
    let firstAudio = false

    bargeInRef.current.reset()
    const session = openSession(characterId, {
      onMessage: (message) => {
        if (stale()) return
        switch (message.type) {
          case 'speech_start':
            if (suppressing.current) break
            speechTimeline.current.begin(message.utterance_id)
            audioOffset = 0
            break
          case 'speech_timing':
            if (!suppressing.current) {
              speechTimeline.current.add(message.utterance_id, message.visemes)
            }
            break
          case 'metrics':
            for (const [name, value] of Object.entries(message.values)) recordMetric(name, value)
            break
          case 'hearing':
            // Provisional: the listener watching themselves be heard. It is
            // replaced by the next one and never acted on.
            setTranscript(message.text)
            setProgressAt(Date.now())
            break
          case 'transcript':
            awaitingReply.current = true
            playerRef.current?.stop()
            speechTimeline.current.clear()
            spokenRef.current = false
            receivedReply.current = false
            transcriptAt = performance.now()
            firstAudio = false
            suppressing.current = false
            setTranscript(message.text)
            setDetail('')
            // A new turn starts with nothing said yet.
            setReply('')
            setSpokenSoFar('')
            setTurnFinished(false)
            setPlaybackDone(false)
            queued.current = []
            pendingExpression.current = null
            setTurnId((previous) => previous + 1)
            // A new turn: whatever was cut off before is finished with, and
            // the next utterance gets a fresh still.
            bargeInRef.current.reset()
            frameSentRef.current = false
            setProgressAt(Date.now())
            setStatus('thinking')
            break
          case 'speaking':
            setProgressAt(Date.now())
            if (suppressing.current) break
            // Held until its audio has actually played. The socket delivers
            // far faster than real time, so revealing on arrival would put the
            // whole reply on screen while she is still on the first sentence.
            queued.current.push({ text: message.text, playedBy: null, ...pendingExpression.current })
            pendingExpression.current = null
            break
          case 'reply':
            awaitingReply.current = false
            receivedReply.current = true
            queued.current = queued.current.filter((item) => item.playedBy !== null)
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
            // Held for the sentence it belongs to. The wire runs seconds
            // ahead of the voice, so applying on arrival moves her body to
            // words she has not said yet.
            setProgressAt(Date.now())
            if (suppressing.current) break
            pendingExpression.current = { gesture: message.gesture, emotion: message.emotion }
            break
          case 'ready':
            if (ready) break
            ready = true
            markConnected()
            sampleRate = message.sample_rate
            player = new PcmPlayer(context, message.sample_rate)
            playerRef.current = player
            break
          case 'audio':
            if (suppressing.current || message.samples.length === 0) break
            spokenRef.current = true
            setPlaybackDone(false)
            setProgressAt(Date.now())
            setStatus('speaking')
            if (!player) {
              player = new PcmPlayer(context, DEFAULT_SAMPLE_RATE)
              playerRef.current = player
            }
            {
              const scheduled = player.enqueue(message.samples)
              const duration = message.samples.length / sampleRate
              speechTimeline.current.schedule(audioOffset, audioOffset + duration, scheduled)
              audioOffset += duration
              if (!firstAudio && message.samples.length > 0) {
                firstAudio = true
                recordMetric('transcript_to_scheduled_audio_ms', performance.now() - transcriptAt +
                  Math.max(0, scheduled - context.currentTime) * 1000)
              }
              // Captions and gesture cues begin at the actual first sample.
              const pending = queued.current.find((item) => item.playedBy === null)
              if (pending) pending.playedBy = scheduled
            }
            break
          case 'interrupted':
            awaitingReply.current = false
            speechTimeline.current.clear()
            queued.current = []
            suppressing.current = false
            pendingExpression.current = null
            setGesture('idle')
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
            if (farewellTimer.current !== null) window.clearInterval(farewellTimer.current)
            const closing = window.setInterval(() => {
              if (stale()) { window.clearInterval(closing); return }
              const done = playerRef.current?.isFinished() ?? true
              if (done || Date.now() - started > FAREWELL_MAX_WAIT_MS) {
                window.clearInterval(closing)
                teardown()
                setStatus('idle')
              }
            }, 150)
            farewellTimer.current = closing
            break
          }
          case 'error':
            awaitingReply.current = false
            speechTimeline.current.clear()
            queued.current = []
            // One failed turn, reported by the server; the conversation goes
            // on. A connection that has actually died arrives as a close.
            setDetail(message.detail)
            playerRef.current?.stop()
            spokenRef.current = false
            setStatus('listening')
            break
          case 'done':
            setTurnFinished(true)
            teardown()
            setStatus('idle')
            break
        }
      },
      onError: (message) => {
        if (stale()) return
        setDetail(message)
        teardown()
        setStatus('error')
      },
      onClose: (event) => {
        if (stale()) return
        // A clean close is the end of the conversation; anything else is a
        // connection that died under us and must be surfaced.
        if (!event.wasClean) setDetail('Connection lost.')
        teardown()
        setStatus(event.wasClean ? 'idle' : 'error')
      },
    }, voiceId)
    sessionRef.current = session

    startCapture((frame) => {
      if (stale()) return
      // Keep real-time silence flowing so STT can finish its current utterance,
      // without feeding TV speech into the next turn while the avatar replies.
      const paused = !allowVoiceInterruption && (awaitingReply.current || spokenRef.current)
      session.sendAudio(paused ? new Int16Array(frame.length) : frame)
      inputLevelRef.current = frameLevel(frame)
      // One still per utterance. Ungated this ran on every audio frame, which
      // is ten JPEG uploads a second and continuous vision-token spend.
      if (cameraRef.current && !pendingFrame.current && !frameSentRef.current) {
        frameSentRef.current = true
        pendingFrame.current = true
        void cameraRef.current
          .grab()
          .then((frame) => (frame && !stale() ? session.sendFrame(frame) : undefined))
          .catch(() => { /* A lost camera frame must not end voice conversation. */ })
          .finally(() => { if (!stale()) pendingFrame.current = false })
      }

      // Only while she is actually speaking. Ungated, the threshold collapses
      // to the noise floor between replies and every ordinary utterance would
      // fire an interrupt.
      const player = playerRef.current
      if (allowVoiceInterruption && spokenRef.current && player) {
        const speaking = player.currentLoudness()
        if (bargeInRef.current.observe(frameLevel(frame), speaking)) {
          spokenRef.current = false
          bargeInRef.current.reset()
          const stoppedAt = performance.now()
          player.stop()
          speechTimeline.current.clear()
          recordMetric('local_interrupt_stop_ms', performance.now() - stoppedAt)
          // Messages already in flight would otherwise restart her audio and
          // add sentences to the caption that were never heard.
          suppressing.current = true
          queued.current = []
          pendingExpression.current = null
          setGesture('idle')
          session.interrupt()
          setStatus('listening')
        }
      }
    }, microphoneAutoVolume)
      .then((capture) => {
        if (stale()) {
          capture.stop()
          return
        }
        captureRef.current = capture
        captureReady = true
        markConnected()
      })
      .catch((error: unknown) => {
        if (stale()) return
        setDetail(error instanceof Error && error.name === 'NotAllowedError'
          ? 'Microphone permission was denied. Allow microphone access in your browser, then start again.'
          : error instanceof Error ? error.message : 'Microphone unavailable.')
        teardown()
        setStatus('error')
      })
      .finally(() => { if (!stale()) startingRef.current = false })
  }, [characterId, voiceId, allowVoiceInterruption, microphoneAutoVolume, teardown])

  const toggleCamera = useCallback(() => {
    const token = ++cameraGeneration.current
    if (cameraStarting.current) {
      cameraStarting.current = false
      return
    }
    if (cameraRef.current) {
      cameraRef.current.stop()
      cameraRef.current = null
      setCameraStream(null)
      return
    }
    cameraStarting.current = true
    startCamera()
      .then((camera) => {
        if (token !== cameraGeneration.current) { camera.stop(); return }
        cameraRef.current = camera
        setCameraStream(camera.stream)
      })
      .catch(() => {
        if (token === cameraGeneration.current) setDetail('Could not open the camera.')
      })
      .finally(() => {
        if (token === cameraGeneration.current) cameraStarting.current = false
      })
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
  // than leaving the user watching a label forever. Any message re-arms it,
  // so a slow reply that is arriving is given its time.
  useEffect(() => {
    if (status !== 'thinking' && status !== 'connecting') return
    const giveUp = window.setTimeout(() => {
      setDetail(status === 'connecting' ? 'Connection timed out. Check microphone permission and try again.' : 'The reply stalled. Start the conversation again.')
      teardown()
      setStatus('error')
    }, status === 'connecting' ? 20_000 : THINKING_TIMEOUT_MS)
    return () => { window.clearTimeout(giveUp) }
  }, [status, progressAt, teardown])

  // Caption and teardown both run on the player's clock rather than on message
  // arrival: audio is delivered far faster than it is heard, so anything keyed
  // to the socket shows the words seconds before she says them.
  useEffect(() => {
    if (status !== 'speaking') return
    let lastClock = playerRef.current?.now ?? 0
    let lastAdvance = Date.now()
    const tick = window.setInterval(() => {
      const player = playerRef.current
      if (!player) return
      if (player.now > lastClock) {
        lastClock = player.now
        lastAdvance = Date.now()
      } else if (!player.isFinished() && Date.now() - lastAdvance > 10_000) {
        setDetail('Audio playback stopped. Start the conversation again to resume audio.')
        teardown()
        setStatus('error')
        return
      }

      const heard = queued.current.filter(
        (pending) => pending.playedBy !== null && pending.playedBy <= player.now,
      )
      if (heard.length > 0) {
        queued.current = queued.current.filter((pending) => !heard.includes(pending))
        setSpokenSoFar((said) =>
          [said, ...heard.map((pending) => pending.text)].filter(Boolean).join(' '),
        )
        // Her body moves with the sentence being heard, not with the wire.
        const cued = heard.filter((pending) => pending.gesture !== undefined).at(-1)
        if (cued?.gesture !== undefined) setGesture(cued.gesture)
        if (cued?.emotion !== undefined) setEmotion(cued.emotion)
      }
      if (player.isFinished() && !receivedReply.current) {
        spokenRef.current = false
        setGesture('idle')
        setStatus('thinking')
      }
      if (player.isFinished() && queued.current.length === 0) {
        setPlaybackDone(true)
        // The turn is over; hands come back down rather than holding the last
        // gesture like a statue.
        setGesture('idle')
        if (receivedReply.current) {
          spokenRef.current = false
          setStatus('listening')
        }
      }
    }, 100)
    return () => { window.clearInterval(tick) }
  }, [status, teardown])


  // Reused between frames so the render loop allocates nothing.
  const featureScratch = useRef<AudioFeatures>({ ...SILENT_FEATURES })
  const features = useCallback(
    () =>
      playerRef.current?.readFeatures(featureScratch.current) ??
      Object.assign(featureScratch.current, SILENT_FEATURES),
    [],
  )

  const mouthCues = useCallback(() => {
    const player = playerRef.current
    return player ? speechTimeline.current.sample(player.now) : null
  }, [])

  return {
    mouthCues,
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
