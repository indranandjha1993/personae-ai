import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { parseExperience, type Experience } from './avatar/config'
import { PixelStreamingStage } from './avatar/PixelStreamingStage'
import { downloadMetrics } from './diagnostics'

import type { AudioFeatures } from './audio/playback'
import { visibleCaption } from './caption'
import './styles.css'
import { useConversation } from './useConversation'

// The 3D stack is most of the bundle, so it loads on demand.
const AvatarStage = lazy(() =>
  import('./avatar/AvatarStage').then((module) => ({ default: module.AvatarStage })),
)


export function App() {
  const [experience, setExperience] = useState<Experience | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/characters', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('failed'))))
      .then((body: unknown) => {
        if (controller.signal.aborted) return
        setExperience(parseExperience(body))
        setLoading(false)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) return
        setLoadError('Could not reach the backend. Please try again.')
        setLoading(false)
      })
    return () => { controller.abort() }
  }, [attempt])

  const character = experience?.character
  const retry = () => {
    setLoadError('')
    setLoading(true)
    setAttempt((value) => value + 1)
  }
  return (
    <div className="app">
      <header className="masthead">
        <h1 className="wordmark">{character?.display_name ?? 'Personae'}</h1>
        <p className="tagline">Personae AI</p>
      </header>
      {loading && <p className="catalogue-state" role="status">Preparing your conversation…</p>}
      {loadError !== '' && <p className="alert" role="alert">{loadError}</p>}
      {!loading && !character && (
        <div className="catalogue-state">
          {loadError === '' && <p>No personalities are available yet. Add a character pack to get started.</p>}
          <button className="text-button" type="button" onClick={retry}>Try again</button>
        </div>
      )}
      {experience && (experience.character.avatar.renderer === 'pixel-streaming'
        ? <PixelStreamingStage avatar={experience.character.avatar} characterId={experience.character.id} />
        : <Conversation {...experience} />)}
      {new URLSearchParams(window.location.search).has('diagnostics') &&
        <button type="button" onClick={downloadMetrics}>Download measurements</button>}
    </div>
  )
}

/**
 * Drives a CSS variable from her voice, once per animation frame.
 *
 * Fast attack and slow release, so the light blooms on the first syllable and
 * decays like a breath. Never React state: this changes sixty times a second.
 */
function InputMeter({ level }: { level: () => number }): React.ReactElement {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let frame = 0
    const tick = (): void => {
      const bar = ref.current
      if (bar) {
        // Speech sits low in the 0..1 range, so the scale is generous.
        const shown = Math.min(1, level() * 6)
        bar.style.setProperty('--level', shown.toFixed(3))
        bar.dataset['hearing'] = shown > 0.06 ? 'yes' : 'no'
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame) }
  }, [level])

  return <div className="input-meter" ref={ref} title="Microphone level" aria-hidden="true" />
}

function useVoiceLight(
  ref: React.RefObject<HTMLDivElement | null>,
  features: () => AudioFeatures,
): void {
  useEffect(() => {
    let frame = 0
    let level = 0
    const tick = (): void => {
      const target = Math.min(1, features().rms * 3.2)
      level = target > level ? level + (target - level) * 0.5 : level * 0.92
      ref.current?.style.setProperty('--voice', level.toFixed(3))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame) }
  }, [features, ref])
}

function Conversation({ character, appearance, voiceId, quality }: Experience) {
  const { id: characterId, display_name: name } = character
  const avatar = appearance.avatar
  const {
    mouthCues,
    status, transcript, reply, gesture, emotion, detail,
    features, spokenSoFar, turnFinished, turnId, inputLevel,
    cameraStream, cameraOn, toggleCamera, start, stop,
  } = useConversation(characterId, voiceId)
  const active = status !== 'idle' && status !== 'error'
  const stage = useRef<HTMLDivElement>(null)
  useVoiceLight(stage, features)

  // Captions are on by default; the toggle turns them off for anyone who would
  // rather hear the line before reading it. Off, her words wait until she has
  // actually finished saying them -- the reply text arrives before the first
  // audio chunk, so status alone would show it during the pause beforehand.
  const [liveCaptions, setLiveCaptions] = useState(true)
  const caption = visibleCaption(spokenSoFar, reply, turnFinished, liveCaptions)

  return (
    <section aria-label="Conversation">
      <div className="stage-frame" data-state={status} ref={stage}>
        <div className="stage-light stage-light--idle" />
        <div className="stage-light stage-light--listen" />
        <div className="stage-light stage-light--speak" />
        <Suspense fallback={<p className="stage-loading" role="status">Loading avatar…</p>}>
          <AvatarStage avatar={avatar} quality={quality} mouthCues={mouthCues} gesture={gesture} emotion={emotion} activity={status} features={features} />
        </Suspense>
        <div className="stage-grain" />
        {cameraStream && <SelfView stream={cameraStream} />}
        <span className="status" data-state={status} role="status" aria-live="polite">
          <span data-testid="status">{status}</span>
        </span>
        {active && <InputMeter level={inputLevel} />}
      </div>
      <div className="hearth" data-state={status} aria-hidden="true" />

      <div className="controls">
        <button type="button" className="talk" data-active={active} onClick={active ? stop : start}>
          {active ? 'End conversation' : 'Start conversation'}
        </button>

        <button
          type="button"
          className="icon-toggle"
          aria-pressed={cameraOn}
          aria-label="Camera"
          onClick={toggleCamera}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
            <rect x="2.5" y="6.5" width="13" height="11" rx="2.5" />
            <path d="M15.5 10.5 21 7.8v8.4l-5.5-2.7z" />
          </svg>
        </button>

        <button
          type="button"
          className="icon-toggle"
          aria-pressed={liveCaptions}
          aria-label="Live captions"
          onClick={() => { setLiveCaptions((on) => !on) }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
            <rect x="2.5" y="5.5" width="19" height="13" rx="3" />
            <path d="M7 12h3M13 12h4" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {!active && (
        <p className="hint">
          {name}&apos;s here. Answers when you pause; interrupt anytime.
        </p>
      )}
      {detail !== '' && <p className="alert" role="alert">{detail}</p>}

      <div className="transcript">
        {transcript !== '' && (
          <p className="line" data-from="you">
            {transcript}
          </p>
        )}
        {caption !== '' && (
          <p className="line" data-from="her" key={turnId} style={{ '--who': `'${name} — '` } as React.CSSProperties}>
            {caption}
          </p>
        )}
      </div>
    </section>
  )
}

function SelfView({ stream }: { stream: MediaStream }) {
  const video = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const element = video.current
    if (!element) return
    element.srcObject = stream
    return () => { element.srcObject = null }
  }, [stream])

  return (
    <div className="self-view">
      <video ref={video} autoPlay muted playsInline aria-label="Your camera" />
    </div>
  )
}
