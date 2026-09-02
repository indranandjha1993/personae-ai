import { describe, expect, it } from 'vitest'

import { visibleCaption } from './caption'

describe('visibleCaption', () => {
  it('shows her words immediately when captions are on', () => {
    expect(visibleCaption('Hello there', false, true)).toBe('Hello there')
  })

  it('withholds them until she has spoken when captions are off', () => {
    expect(visibleCaption('Hello there', false, false)).toBe('')
    expect(visibleCaption('Hello there', true, false)).toBe('Hello there')
  })

  it('shows nothing before there is a reply at all', () => {
    expect(visibleCaption('', false, true)).toBe('')
    expect(visibleCaption('', true, false)).toBe('')
  })
})

describe('when audio precedes the text', () => {
  it('shows her words once the reply arrives at the end of a turn', () => {
    // Sentences are synthesised as they stream, so the reply message is the
    // last thing in a turn rather than the first. Treating it as the start of
    // an unspoken reply withheld the caption forever.
    const spoken = true
    expect(visibleCaption('All done.', spoken, false)).toBe('All done.')
  })

  it('still withholds a reply that genuinely has not been spoken', () => {
    expect(visibleCaption('Not yet said.', false, false)).toBe('')
  })
})
