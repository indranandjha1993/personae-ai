import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from './App'
import { DEFAULT_AVATAR } from './avatar/config'

vi.mock('./avatar/AvatarStage', () => ({ AvatarStage: ({ avatar, quality }: { avatar: { model_url: string }; quality: string }) =>
  <div data-testid="avatar" data-quality={quality}>{avatar.model_url}</div> }))
vi.mock('./useConversation', () => ({ useConversation: (characterId: string, voiceId: string) => {
  const [status, setStatus] = useState('idle')
  const [transcript, setTranscript] = useState('')
  return {
    status, transcript, reply: '', gesture: 'idle', emotion: 'neutral', detail: '',
    features: () => ({ rms: 0 }), mouthCues: () => null, inputLevel: () => 0,
    spokenSoFar: '', turnFinished: false, turnId: 0, cameraStream: null, cameraOn: false,
    toggleCamera: () => {}, start: () => { setStatus('listening'); setTranscript(`${characterId} with ${voiceId}`) },
    stop: () => { setStatus('idle') },
  }
} }))
const characters = [
  { id: 'bundled/coach', display_name: 'Coach', avatar: { ...DEFAULT_AVATAR, model_url: '/models/coach.vrm' } },
  { id: 'bundled/seed', display_name: 'Wren', avatar: DEFAULT_AVATAR },
]
const voices = [
  { id: 'default', label: 'Configured voice', mode: 'mock' },
  { id: 'local', label: 'Local voice', mode: 'local' },
]
function setupFetch(catalogue = characters) {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve({ ok: true,
    json: () => Promise.resolve(url === '/api/voices' ? { voices } : { characters: catalogue }),
  })))
}
beforeEach(() => { setupFetch() })
afterEach(() => { vi.unstubAllGlobals() })

it('prefers Wren, labels mock audio honestly, and preserves live sessions on appearance changes', async () => {
  render(<App />)
  await screen.findByRole('heading', { name: 'Wren' })
  await userEvent.click(screen.getByText('Make it yours'))
  expect(screen.getByRole('option', { name: 'Demo voice' })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))
  expect(screen.getByLabelText('Personality')).toBeDisabled()
  expect(screen.getByLabelText('Voice')).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Appearance'), 'bundled/coach')
  await userEvent.selectOptions(screen.getByLabelText('Render quality'), 'low')
  expect(screen.getByTestId('avatar')).toHaveTextContent('/models/coach.vrm')
  expect(screen.getByTestId('avatar')).toHaveAttribute('data-quality', 'low')
  expect(screen.getByRole('heading', { name: 'Wren' })).toBeInTheDocument()
  expect(screen.getByTestId('status')).toHaveTextContent('listening')
  expect(screen.getByText('bundled/seed with default')).toBeInTheDocument()
})

it('starts fresh for personality and voice changes while preserving appearance', async () => {
  render(<App />)
  await screen.findByRole('button', { name: 'Start conversation' })
  await userEvent.click(screen.getByText('Make it yours'))
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))
  await userEvent.click(screen.getByRole('button', { name: 'End conversation' }))
  await userEvent.selectOptions(screen.getByLabelText('Personality'), 'bundled/coach')
  expect(screen.queryByText('bundled/seed with default')).not.toBeInTheDocument()
  expect(screen.getByTestId('avatar')).toHaveTextContent(DEFAULT_AVATAR.model_url)
  await userEvent.click(screen.getByText('Make it yours'))
  await userEvent.selectOptions(screen.getByLabelText('Voice'), 'local')
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))
  expect(screen.getByText('bundled/coach with local')).toBeInTheDocument()
})

it('recovers from an empty catalogue with a retry', async () => {
  setupFetch([])
  render(<App />)
  expect(await screen.findByText(/No personalities are available/)).toBeInTheDocument()
  setupFetch()
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('heading', { name: 'Wren' })).toBeInTheDocument()
})

it('keeps the configured voice usable on older servers', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve({ ok: url !== '/api/voices',
    json: () => Promise.resolve({ characters }),
  })))
  render(<App />)
  await screen.findByRole('heading', { name: 'Wren' })
  await userEvent.click(screen.getByText('Make it yours'))
  expect(await screen.findByText(/Voice options unavailable/)).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'Configured voice' })).toBeInTheDocument()
})


it('switches from a hosted experience to a valid browser appearance', async () => {
  const hosted = {
    id: 'bundled/hosted', display_name: 'Hosted',
    avatar: { ...DEFAULT_AVATAR, renderer: 'pixel-streaming' as const, player_url: 'https://player.example/session' },
  }
  // Starting with a hosted pack exercises an appearance initially pointing to that pack.
  setupFetch([hosted, ...characters.filter((entry) => entry.id === 'bundled/coach')])
  render(<App />)
  expect(await screen.findByTitle('Live avatar')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Experience'), 'bundled/coach')
  expect(await screen.findByTestId('avatar')).toHaveTextContent('/models/coach.vrm')
  expect(screen.queryByTitle('Live avatar')).not.toBeInTheDocument()
  await userEvent.click(screen.getByText('Make it yours'))
  expect(screen.getByLabelText('Appearance')).toHaveValue('bundled/coach')
  expect(screen.getByText(/Answers when you pause; interrupt anytime/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))
  expect(screen.getByText('bundled/coach with default')).toBeInTheDocument()
})
