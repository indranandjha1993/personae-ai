import { lazy, Suspense, useEffect, useState } from 'react'

import './styles.css'
import { useConversation } from './useConversation'

// The 3D stack is roughly two thirds of the bundle. Loading it separately keeps
// the first paint fast and costs nothing for anyone without a model.
const AvatarStage = lazy(() =>
  import('./avatar/AvatarStage').then((module) => ({ default: module.AvatarStage })),
)

interface CharacterSummary {
  id: string
  display_name: string
  theme: { primary: string; secondary: string }
  expression: { gestures: string[]; emotions: string[] }
}

export function App() {
  const [characters, setCharacters] = useState<CharacterSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/characters', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('failed'))))
      .then((body: { characters: CharacterSummary[] }) => {
        setCharacters(body.characters)
        setSelected(body.characters[0]?.id ?? null)
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === 'AbortError') return
        setLoadError('Could not load characters. Is the backend running?')
      })
    return () => { controller.abort() }
  }, [])

  const active = characters.find((character) => character.id === selected)

  return (
    <main>
      <h1>Personae AI</h1>
      <p className="tagline">Pick a voice, then talk to it.</p>

      {loadError !== '' && <p className="alert" role="alert">{loadError}</p>}

      <ul className="characters" aria-label="Characters">
        {characters.map((character) => (
          <li key={character.id}>
            <button
              type="button"
              className="character"
              aria-pressed={selected === character.id}
              style={{ '--dot': character.theme.primary } as React.CSSProperties}
              onClick={() => { setSelected(character.id) }}
            >
              {character.display_name}
            </button>
          </li>
        ))}
      </ul>

      {active && <Conversation key={active.id} characterId={active.id} />}
    </main>
  )
}

function Conversation({ characterId }: { characterId: string }) {
  const { status, transcript, reply, gesture, emotion, detail, loudness, start, stop } =
    useConversation(characterId)
  const listening = status === 'listening'

  return (
    <section className="panel" aria-label="Conversation">
      <Suspense fallback={<div className="stage stage--empty">Loading avatar…</div>}>
        <AvatarStage gesture={gesture} emotion={emotion} loudness={loudness} />
      </Suspense>

      <div className="row">
        <button
          type="button"
          className="talk"
          data-listening={listening}
          onClick={listening ? stop : start}
        >
          {listening ? 'Stop speaking' : 'Start speaking'}
        </button>
        <span className="status" data-state={status}>
          <span data-testid="status">{status}</span>
        </span>
      </div>

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

      <p className="cues">
        Gesture: {gesture} · Emotion: {emotion}
      </p>
    </section>
  )
}
