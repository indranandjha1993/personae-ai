import { useEffect, useState } from 'react'

import { useConversation } from './useConversation'

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

  return (
    <main>
      <h1>Personae AI</h1>
      {loadError !== '' && <p role="alert">{loadError}</p>}
      <ul aria-label="Characters">
        {characters.map((character) => (
          <li key={character.id}>
            <button
              type="button"
              aria-pressed={selected === character.id}
              onClick={() => { setSelected(character.id) }}
            >
              {character.display_name}
            </button>
          </li>
        ))}
      </ul>
      {selected !== null && <Conversation characterId={selected} />}
    </main>
  )
}

function Conversation({ characterId }: { characterId: string }) {
  const { status, transcript, reply, gesture, emotion, detail, start, stop } =
    useConversation(characterId)
  const listening = status === 'listening'

  return (
    <section aria-label="Conversation">
      <p>
        Status: <span data-testid="status">{status}</span>
      </p>
      <button type="button" onClick={listening ? stop : start}>
        {listening ? 'Stop speaking' : 'Start speaking'}
      </button>
      {detail !== '' && <p role="alert">{detail}</p>}
      {transcript !== '' && <p>You said: {transcript}</p>}
      {reply !== '' && <p>Reply: {reply}</p>}
      <p>
        Gesture: {gesture} / Emotion: {emotion}
      </p>
    </section>
  )
}
