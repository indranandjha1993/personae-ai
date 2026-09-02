import { describe, expect, it } from 'vitest'

import { visibleCaption } from './caption'

describe('visibleCaption with captions on', () => {
  it('keeps pace with her voice, sentence by sentence', () => {
    expect(visibleCaption('First thought.', '', false, true)).toBe('First thought.')
    expect(visibleCaption('First thought. Second.', '', false, true)).toBe(
      'First thought. Second.',
    )
  })

  it('prefers the full reply once the turn closes', () => {
    // The splitter can drop a trailing fragment; the full text supersedes it.
    expect(visibleCaption('First thought.', 'First thought. And more.', true, true)).toBe(
      'First thought. And more.',
    )
  })

  it('shows nothing before she has said anything', () => {
    expect(visibleCaption('', '', false, true)).toBe('')
  })
})

describe('visibleCaption with captions off', () => {
  it('withholds the text while she is still speaking', () => {
    // This is the whole point of the toggle: hear the line before reading it.
    expect(visibleCaption('First thought.', '', false, false)).toBe('')
  })

  it('shows the reply once the turn has finished', () => {
    expect(visibleCaption('First thought.', 'First thought. And more.', true, false)).toBe(
      'First thought. And more.',
    )
  })
})

describe('when a turn is cut short', () => {
  it('shows what she managed to say, since no full reply arrives', () => {
    // A barge-in ends the turn without a reply message; without this the
    // caption stays blank and the half-heard words are lost.
    expect(visibleCaption('First thought.', '', true, false)).toBe('First thought.')
  })

  it('still shows nothing if she was cut off before speaking', () => {
    expect(visibleCaption('', '', true, false)).toBe('')
  })
})

describe('while she is still speaking with captions on', () => {
  it('shows only what has been heard, not the reply already on the wire', () => {
    // The full text arrives long before the audio finishes; showing it early
    // puts the ending on screen while she is still on the first sentence.
    expect(visibleCaption('First.', 'First. Second. Third.', false, true)).toBe('First.')
  })

  it('settles on the cleaned full reply once the turn is done', () => {
    expect(visibleCaption('First. Second.', 'First. Second.', true, true)).toBe('First. Second.')
  })
})
