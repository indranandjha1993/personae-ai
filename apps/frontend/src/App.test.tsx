import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

// jsdom has no WebGL, so the 3D stage cannot render here.
vi.mock('./avatar/AvatarStage', () => ({ AvatarStage: () => null }))

const BODY = { characters: [{ id: 'bundled/seed', display_name: 'Seed' }] }

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
    expect(await screen.findByLabelText('Camera')).not.toBeChecked()
  })

  it('reports a backend that cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')
  })
})
