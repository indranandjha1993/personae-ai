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
const experience = { allow_voice_interruption: true, microphone_auto_volume: true, character_id: 'bundled/coach', appearance_id: 'bundled/seed', voice_id: 'local:af_heart', quality: 'low' }
function setupFetch(config: unknown = experience) {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true,
    json: () => Promise.resolve({ characters, experience: config }),
  })))
}
beforeEach(() => { setupFetch() })
afterEach(() => { vi.unstubAllGlobals() })

it('uses server settings independently and exposes no customization controls', async () => {
  render(<App />)
  await screen.findByRole('heading', { name: 'Coach' })
  expect(await screen.findByTestId('avatar')).toHaveTextContent('/models/seed-san.vrm')
  expect(screen.getByTestId('avatar')).toHaveAttribute('data-quality', 'low')
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.queryByText('Make it yours')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))
  expect(screen.getByText('bundled/coach with local:af_heart')).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('does not silently fall back to Wren for an invalid configured character', async () => {
  setupFetch({ ...experience, character_id: 'missing/character' })
  render(<App />)
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Start conversation' })).not.toBeInTheDocument()
  setupFetch()
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('heading', { name: 'Coach' })).toBeInTheDocument()
})

it('rejects an old response without deployment configuration', async () => {
  setupFetch(null)
  render(<App />)
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Start conversation' })).not.toBeInTheDocument()
})
