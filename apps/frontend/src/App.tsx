import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { parseCharacters, parseVoices, type Character, type VoiceOption } from './avatar/config'
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
  const [characters, setCharacters] = useState<Character[]>([])
  const [characterId, setCharacterId] = useState('')
  const [appearanceId, setAppearanceId] = useState('')
  const [voiceId, setVoiceId] = useState('default')
  const [voices, setVoices] = useState<VoiceOption[]>([{ id: 'default', label: 'Configured voice', mode: 'live' }])
  const [voiceNotice, setVoiceNotice] = useState('')
  const [quality, setQuality] = useState<'auto' | 'high' | 'low'>('auto')
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/characters', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('failed'))))
      .then((body: unknown) => {
        if (controller.signal.aborted) return
        const catalogue = parseCharacters(body)
        const first = catalogue.find((entry) => entry.id === 'bundled/seed') ?? catalogue[0]
        setCharacters(catalogue)
        setCharacterId(first?.id ?? '')
        setAppearanceId(first?.id ?? '')
        setLoading(false)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) return
        setLoadError('Could not reach the backend. Please try again.')
        setLoading(false)
      })
    fetch('/api/voices', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('failed'))))
      .then((body: unknown) => {
        if (!controller.signal.aborted) {
          setVoices(parseVoices(body))
          setVoiceNotice('')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setVoiceNotice('Voice options unavailable. Using the configured voice.')
      })
    return () => { controller.abort() }
  }, [attempt])

  const character = characters.find((entry) => entry.id === characterId)
  // A hosted experience is never a model for the local browser renderer.
  const appearance = characters.find((entry) => entry.id === appearanceId && entry.avatar.renderer === 'vrm') ?? character
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
      {character && appearance && (character.avatar.renderer === 'pixel-streaming'
        ? <>
            <label className="hosted-choice">Experience
              <select value={character.id} onChange={(event) => {
                setCharacterId(event.target.value)
                setAppearanceId(event.target.value)
              }}>
                {characters.map((entry) => <option value={entry.id} key={entry.id}>{entry.display_name}{entry.avatar.renderer === 'pixel-streaming' ? ' · Hosted avatar' : ' · Browser avatar'}</option>)}
              </select>
            </label>
            <p className="customize-note">This hosted experience manages its own voice and appearance.</p>
            <PixelStreamingStage avatar={character.avatar} characterId={character.id} />
          </>
        : <Conversation key={`${character.id}:${voiceId}`} character={character} appearance={appearance}
            characters={characters} onCharacterChange={setCharacterId} onAppearanceChange={setAppearanceId}
            voiceId={voiceId} voices={voices} voiceNotice={voiceNotice} onVoiceChange={setVoiceId}
            quality={quality} onQualityChange={setQuality} />)}
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

interface ConversationProps {
  character: Character
  appearance: Character
  characters: Character[]
  onCharacterChange: (id: string) => void
  onAppearanceChange: (id: string) => void
  voiceId: string
  voices: VoiceOption[]
  voiceNotice: string
  onVoiceChange: (id: string) => void
  quality: 'auto' | 'high' | 'low'
  onQualityChange: (quality: 'auto' | 'high' | 'low') => void
}

function Conversation({ character, appearance, characters, onCharacterChange, onAppearanceChange,
  voiceId, voices, voiceNotice, onVoiceChange, quality, onQualityChange }: ConversationProps) {
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
      <details className="customize">
        <summary>
          <span className="customize-title">Make it yours</span>
          <span className="customize-summary">{name} <span aria-hidden="true">/</span> {voices.find((voice) => voice.id === voiceId)?.label ?? 'Configured voice'}</span>
          <span className="customize-action">Customize <span aria-hidden="true">+</span></span>
        </summary>
        <div className="customize-fields">
          <label>Personality
            <select value={characterId} disabled={active} onChange={(event) => { onCharacterChange(event.target.value) }} aria-describedby="customize-timing">
              {characters.map((entry) => <option key={entry.id} value={entry.id}>{entry.display_name}{entry.avatar.renderer === 'pixel-streaming' ? ' · Hosted experience' : ''}</option>)}
            </select>
          </label>
          <label>Appearance
            <select value={appearance.id} onChange={(event) => { onAppearanceChange(event.target.value) }} aria-describedby="appearance-note">
              {characters.filter((entry) => entry.avatar.renderer === 'vrm').map((entry) => <option key={entry.id} value={entry.id}>{entry.display_name}</option>)}
            </select>
          </label>
          <label>Voice
            <select value={voiceId} disabled={active} onChange={(event) => { onVoiceChange(event.target.value) }} aria-describedby="customize-timing">
              {voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.mode === 'mock' ? 'Demo voice' : voice.label}</option>)}
            </select>
          </label>
          <label>Render quality
            <select value={quality} onChange={(event) => {
              const value = event.target.value
              if (value === 'auto' || value === 'high' || value === 'low') onQualityChange(value)
            }}>
              <option value="auto">Auto</option><option value="high">High</option><option value="low">Low</option>
            </select>
          </label>
        </div>
        <p className="customize-note" id="customize-timing">{active
          ? 'End this conversation to change personality or voice. Appearance and quality can change anytime.'
          : 'Changing personality or voice starts a fresh conversation. Appearance and quality keep your conversation.'}</p>
        <p className="customize-note" id="appearance-note">{characters.filter((entry) => entry.avatar.model_url === appearance.avatar.model_url).length > 1
          ? 'Some personalities share the same avatar. Personality and appearance are independent.'
          : 'Appearance is independent of personality.'} Auto balances clarity and device performance.</p>
        {voiceNotice !== '' && <p className="customize-note" role="status">{voiceNotice}</p>}
        {voices.find((voice) => voice.id === voiceId)?.mode === 'mock' && <p className="customize-note">Demo voice plays sample audio, not generated speech.</p>}
      </details>
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
