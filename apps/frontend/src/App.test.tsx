import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

// jsdom has no WebGL, so the 3D stage cannot render here.
vi.mock('./avatar/AvatarStage', () => ({ AvatarStage: () => null }))

const BODY = { characters: [{ id: 'bundled/seed', display_name: 'Wren' }] }

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
    expect(screen.getByText(/talk over her to cut in/i)).toBeInTheDocument()
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

  it('credits the avatar, which its licence requires', async () => {
    render(<App />)
    expect(await screen.findByText(/VRM Public License/)).toBeInTheDocument()
  })

  it('reports a backend that cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')
  })
})
