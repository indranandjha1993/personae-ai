import { describe, expect, it } from 'vitest'

import { fittedSize } from './camera'

describe('fittedSize', () => {
  it('leaves a small frame alone', () => {
    expect(fittedSize(320, 240)).toEqual({ width: 320, height: 240 })
  })

  it('scales a large frame down to the long edge', () => {
    expect(fittedSize(1920, 1080)).toEqual({ width: 768, height: 432 })
  })

  it('preserves aspect ratio for portrait frames', () => {
    expect(fittedSize(1080, 1920)).toEqual({ width: 432, height: 768 })
  })

  it('never enlarges beyond the original', () => {
    const { width } = fittedSize(100, 100, 768)
    expect(width).toBe(100)
  })
})
