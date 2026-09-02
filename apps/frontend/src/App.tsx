import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import './styles.css'
import { useConversation } from './useConversation'

// The 3D stack is most of the bundle, so it loads on demand.
const AvatarStage = lazy(() =>
  import('./avatar/AvatarStage').then((module) => ({ default: module.AvatarStage })),
)

interface Character {
  id: string
  display_name: string
}

export function App() {
  const [character, setCharacter] = useState<Character | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/characters', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('failed'))))
      .then((body: { characters: Character[] }) => { setCharacter(body.characters[0] ?? null) })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === 'AbortError') return
        setLoadError('Could not reach the backend.')
      })
    return () => { controller.abort() }
  }, [])

  return (
    <div className="app">
      <header className="masthead">
        <h1 className="wordmark">
          Personae <span>AI</span>
        </h1>
        {character && <p className="hint">Talking with {character.display_name}</p>}
      </header>
      {loadError !== '' && <p className="alert" role="alert">{loadError}</p>}
      {character && <Conversation characterId={character.id} />}
    </div>
  )
}

function Conversation({ characterId }: { characterId: string }) {
  const {
    status, transcript, reply, gesture, emotion, detail,
    features, cameraStream, cameraOn, toggleCamera, start, stop,
  } = useConversation(characterId)
  const active = status !== 'idle' && status !== 'error'

  return (
    <section aria-label="Conversation">
      <div className="stage-frame">
        <Suspense fallback={null}>
          <AvatarStage
            gesture={gesture}
            emotion={emotion}
            activity={status}
            features={features}
          />
        </Suspense>
        <span className="badge" data-state={status}>
          <span data-testid="status">{status}</span>
        </span>
        {cameraStream && <SelfView stream={cameraStream} />}
      </div>
      <p className="credit">Seed-san by VirtualCast, Inc. — VRM Public License 1.0</p>

      <div className="controls">
        <button type="button" className="talk" data-active={active} onClick={active ? stop : start}>
          {active ? 'End conversation' : 'Start conversation'}
        </button>

        <label className="toggle">
          <input type="checkbox" checked={cameraOn} onChange={toggleCamera} />
          Camera
        </label>
      </div>

      {!active && (
        <p className="hint">She answers when you pause. Talk over her to cut in.</p>
      )}
      {detail !== '' && <p className="alert" role="alert">{detail}</p>}

      <div className="transcript">
        {transcript !== '' && (
          <p className="bubble" data-from="you">
            <b>You</b>
            {transcript}
          </p>
        )}
        {reply !== '' && (
          <p className="bubble" data-from="her">
            <b>Her</b>
            {reply}
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
