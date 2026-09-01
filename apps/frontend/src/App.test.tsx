import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

// jsdom has no WebGL, so the 3D stage cannot render here. These tests cover the
// character picker and conversation state; the avatar's own logic is tested in
// src/avatar/expression-map.test.ts and verified in a real browser.
vi.mock('./avatar/AvatarStage', () => ({
  AvatarStage: () => null,
}))

const CHARACTERS = {
  characters: [
    {
      id: 'bundled/armored-inventor',
      display_name: 'The Armored Inventor',
      theme: { primary: '#c8102e', secondary: '#ffc82e' },
      expression: { gestures: ['idle'], emotions: ['neutral'] },
    },
    {
      id: 'bundled/storm-caller',
      display_name: 'The Storm-Caller',
      theme: { primary: '#1e3a8a', secondary: '#93c5fd' },
      expression: { gestures: ['idle'], emotions: ['neutral'] },
    },
  ],
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(CHARACTERS) })),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('lists the characters the backend reports', async () => {
    render(<App />)
    expect(await screen.findByRole('button', { name: 'The Armored Inventor' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'The Storm-Caller' })).toBeInTheDocument()
  })

  it('selects the first character by default', async () => {
    render(<App />)
    const first = await screen.findByRole('button', { name: 'The Armored Inventor' })
    expect(first).toHaveAttribute('aria-pressed', 'true')
  })

  it('lets a different character be chosen', async () => {
    render(<App />)
    const second = await screen.findByRole('button', { name: 'The Storm-Caller' })
    await userEvent.click(second)
    expect(second).toHaveAttribute('aria-pressed', 'true')
  })

  it('reports a backend that cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false })))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load characters')
  })

  it('starts in the idle state', async () => {
    render(<App />)
    await waitFor(() => { expect(screen.getByTestId('status')).toHaveTextContent('idle') })
  })
})
