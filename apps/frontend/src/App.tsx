import { lazy, Suspense, useEffect, useState } from 'react'

import './styles.css'
import { useConversation, type Mode } from './useConversation'

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
      .then((body: { characters: Character[] }) => {
        setCharacter(body.characters[0] ?? null)
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === 'AbortError') return
        setLoadError('Could not reach the backend.')
      })
    return () => { controller.abort() }
  }, [])

  return (
    <main>
      <h1>Personae AI</h1>
      <p className="tagline">Speak, and she answers aloud.</p>
      {loadError !== '' && <p className="alert" role="alert">{loadError}</p>}
      {character && <Conversation characterId={character.id} />}
    </main>
  )
}

function startLabel(mode: Mode, status: string): string {
  if (status === 'idle' || status === 'error') {
    return mode === 'live' ? 'Start conversation' : 'Start speaking'
  }
  return mode === 'live' ? 'End conversation' : 'Stop speaking'
}

function Conversation({ characterId }: { characterId: string }) {
  const [mode, setMode] = useState<Mode>('turn')
  const { status, transcript, reply, gesture, emotion, detail, loudness, start, stop } =
    useConversation(characterId, mode)
  const active = status !== 'idle' && status !== 'error'

  return (
    <section className="panel" aria-label="Conversation">
      <Suspense fallback={<div className="stage" />}>
        <AvatarStage
          gesture={gesture}
          emotion={emotion}
          activity={status}
          loudness={loudness}
        />
      </Suspense>

      <div className="row">
        <button
          type="button"
          className="talk"
          data-listening={active}
          onClick={active ? stop : start}
        >
          {startLabel(mode, status)}
        </button>
        <span className="status" data-state={status}>
          <span data-testid="status">{status}</span>
        </span>
        <label className="mode">
          <input
            type="checkbox"
            checked={mode === 'live'}
            disabled={active}
            onChange={(event) => { setMode(event.target.checked ? 'live' : 'turn') }}
          />
          Live conversation
        </label>
      </div>
      {mode === 'live' && !active && (
        <p className="hint">
          She listens continuously and answers when you pause. Talk over her to cut in.
        </p>
      )}

      {detail !== '' && <p className="alert" role="alert">{detail}</p>}

      {transcript !== '' && (
        <p className="line">
          <span>You said</span>
          {transcript}
        </p>
      )}

      {reply !== '' && (
        <p className="line">
          <span>Reply</span>
          {reply}
        </p>
      )}
    </section>
  )
}
