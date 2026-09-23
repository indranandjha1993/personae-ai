import { parseCharacters } from '../experience-config'
import { expect, it } from 'vitest'
import { DEFAULT_AVATAR, parseAvatar } from './config'

it('accepts older character summaries and validates configured assets', () => {
  expect(parseCharacters({ characters: [{ id: 'pack/person', display_name: 'Person' }] })[0]?.avatar)
    .toEqual(DEFAULT_AVATAR)
  expect(parseAvatar({ ...DEFAULT_AVATAR, model_url: '/licensed/portrait.vrm' }).model_url)
    .toBe('/licensed/portrait.vrm')
  expect(() => parseAvatar({ ...DEFAULT_AVATAR, player_url: 'javascript:alert(1)' })).toThrow()
  expect(() => parseAvatar({ ...DEFAULT_AVATAR, renderer: 'pixel-streaming' })).toThrow()
})

it('rejects duplicate and empty character identifiers', () => {
  expect(() => parseCharacters({ characters: [{ id: '', display_name: 'Person' }] })).toThrow()
  expect(() => parseCharacters({ characters: [
    { id: 'person', display_name: 'Person' }, { id: 'person', display_name: 'Another' },
  ] })).toThrow()
})
