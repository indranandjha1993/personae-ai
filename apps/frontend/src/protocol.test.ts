import { describe, expect, it } from 'vitest'

import { audioFrom, decodePcm, parseServerMessage } from './protocol'

describe('parseServerMessage', () => {
  it('accepts each known message type', () => {
    expect(parseServerMessage({ type: 'transcript', text: 'hi' })).toEqual({
      type: 'transcript',
      text: 'hi',
    })
    expect(parseServerMessage({ type: 'done' })).toEqual({ type: 'done' })
    expect(parseServerMessage({ type: 'expression', gesture: 'idle', emotion: 'neutral' })).toEqual(
      { type: 'expression', gesture: 'idle', emotion: 'neutral' },
    )
  })

  it('rejects unknown or malformed messages rather than trusting them', () => {
    expect(parseServerMessage({ type: 'shutdown' })).toBeNull()
    expect(parseServerMessage({ type: 'transcript' })).toBeNull()
    expect(parseServerMessage({ type: 'transcript', text: 42 })).toBeNull()
    expect(parseServerMessage(null)).toBeNull()
    expect(parseServerMessage('transcript')).toBeNull()
  })
})

describe('decodePcm', () => {
  it('decodes base64 into 16-bit samples', () => {
    // 0x0100 little-endian is 1; 0x0200 is 2.
    const samples = decodePcm(btoa('\x01\x00\x02\x00'))
    expect(Array.from(samples)).toEqual([1, 2])
  })

  it('ignores a trailing odd byte rather than throwing', () => {
    expect(decodePcm(btoa('\x01\x00\x02')).length).toBe(1)
  })
})

describe('audioFrom', () => {
  it('reads a binary frame as little-endian 16-bit samples', () => {
    const frame = new Uint8Array([0x01, 0x00, 0x02, 0x00]).buffer
    expect(Array.from(audioFrom(frame).samples)).toEqual([1, 2])
  })

  it('drops a trailing odd byte rather than shifting every sample', () => {
    const frame = new Uint8Array([0x01, 0x00, 0x02]).buffer
    expect(audioFrom(frame).samples.length).toBe(1)
  })
})
