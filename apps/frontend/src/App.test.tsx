import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

// jsdom has no WebGL, so the 3D stage cannot render here.
vi.mock('./avatar/AvatarStage', () => ({ AvatarStage: () => null }))

const BODY = { experience: { barge_in_enabled: true, microphone_auto_gain: true, character_id: 'bundled/seed', appearance_id: 'bundled/seed', voice_id: 'default', quality: 'auto' }, characters: [{ id: 'bundled/seed', display_name: 'Wren' }] }

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(BODY) })),
  )
})

afterEach(() => { vi.unstubAllGlobals() })

describe('App', () => {
  it('starts a conversation with the character the backend reports', async () => {
    render(<App />)
    await waitFor(() => { expect(screen.getByTestId('status')).toHaveTextContent('idle') })
    expect(screen.getByRole('button', { name: 'Start conversation' })).toBeInTheDocument()
  })

  it('explains how the conversation works before it starts', async () => {
    render(<App />)
    expect(
      await screen.findByRole('button', { name: 'Start conversation' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Answers when you pause; interrupt anytime/i)).toBeInTheDocument()
  })

  it('offers a camera the conversation can see through', async () => {
    render(<App />)
    const camera = await screen.findByRole('button', { name: 'Camera' })
    expect(camera).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows captions by default and lets them be turned off', async () => {
    render(<App />)
    const captions = await screen.findByRole('button', { name: 'Live captions' })
    expect(captions).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(captions)
    expect(captions).toHaveAttribute('aria-pressed', 'false')
  })

  it('leads with her name rather than the product', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Wren' })).toBeInTheDocument()
    expect(screen.getByText(/Wren's here/)).toBeInTheDocument()
  })

  it('keeps the model out of the scene, so only she is on screen', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Wren' })).toBeInTheDocument()
    expect(screen.queryByText(/VRM Public License|Seed-san/)).not.toBeInTheDocument()
  })

  it('reports a backend that cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')
  })
})

it('uses the hosted player without starting a second local conversation', async () => {
  const { DEFAULT_AVATAR } = await import('./avatar/config')
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({
    experience: { barge_in_enabled: true, microphone_auto_gain: true, character_id: 'local/person', appearance_id: 'local/person', voice_id: 'default', quality: 'auto' },
    characters: [{ id: 'local/person', display_name: 'Person', avatar: {
      ...DEFAULT_AVATAR, renderer: 'pixel-streaming', player_url: 'https://player.example/session',
    } }],
  }) })))
  render(<App />)
  const frame = await screen.findByTitle('Live avatar')
  expect(frame).toHaveAttribute('src', 'https://player.example/session?character=local%2Fperson')
  expect(screen.queryByRole('button', { name: 'Start conversation' })).not.toBeInTheDocument()
})
