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
