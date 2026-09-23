import type { MouthChannel } from '../audio/speech-timeline'

export interface AvatarConfig {
  renderer: 'vrm' | 'pixel-streaming'
  model_url: string
  motions_url: string
  player_url: string | null
  mouth_map: Partial<Record<MouthChannel, string>>
  hidden_meshes: string[]
}
export const DEFAULT_AVATAR: AvatarConfig = {
  renderer: 'vrm', model_url: '/models/seed-san.vrm', motions_url: '/motions/index.json',
  player_url: null, mouth_map: { aa: 'aa', ih: 'ih', ou: 'ou', ee: 'ee', oh: 'oh' }, hidden_meshes: [],
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function safeUrl(value: unknown): value is string {
  return typeof value === 'string' && !value.includes('\\') &&
    ((value.startsWith('/') && !value.startsWith('//')) || value.startsWith('https://'))
}
export function parseAvatar(raw: unknown): AvatarConfig {
  if (raw === undefined) return DEFAULT_AVATAR
  if (!record(raw) || !['vrm', 'pixel-streaming'].includes(String(raw['renderer'])) ||
    !safeUrl(raw['model_url']) || !safeUrl(raw['motions_url'])) throw new Error('Invalid avatar')
  const renderer = raw['renderer'] === 'pixel-streaming' ? 'pixel-streaming' : 'vrm'
  const player = raw['player_url']
  if (player !== null && !safeUrl(player)) throw new Error('Invalid player URL')
  if (renderer === 'pixel-streaming' && !player) throw new Error('Missing player URL')
  const map = raw['mouth_map']
  if (!record(map)) throw new Error('Invalid mouth map')
  const mouth: AvatarConfig['mouth_map'] = {}
  for (const name of ['aa', 'ih', 'ou', 'ee', 'oh', 'closed'] as const) {
    const value = map[name]
    if (value !== undefined && (typeof value !== 'string' || !value)) throw new Error('Invalid morph')
    if (typeof value === 'string') mouth[name] = value
  }
  const hidden: unknown = raw['hidden_meshes']
  if (!Array.isArray(hidden) || !hidden.every((name: unknown): name is string => typeof name === 'string')) {
    throw new Error('Invalid hidden meshes')
  }
  return { renderer, model_url: raw['model_url'], motions_url: raw['motions_url'],
    player_url: player, mouth_map: mouth, hidden_meshes: hidden }
}
