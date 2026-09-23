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
export interface Character { id: string; display_name: string; avatar: AvatarConfig }
export function parseCharacters(body: unknown): Character[] {
  if (!record(body) || !Array.isArray(body['characters'])) throw new Error('Invalid characters')
  const seen = new Set<string>()
  return body['characters'].map((entry: unknown) => {
    if (!record(entry) || typeof entry['id'] !== 'string' || !entry['id'].trim() || typeof entry['display_name'] !== 'string' || !entry['display_name'].trim()) {
      throw new Error('Invalid character')
    }
    if (seen.has(entry['id'])) throw new Error('Duplicate character')
    seen.add(entry['id'])
    return { id: entry['id'], display_name: entry['display_name'], avatar: parseAvatar(entry['avatar']) }
  })
}

export interface VoiceOption { id: string; label: string; mode: 'live' | 'mock' | 'local' }
export function parseVoices(body: unknown): VoiceOption[] {
  if (!record(body) || !Array.isArray(body['voices'])) throw new Error('Invalid voices')
  const seen = new Set<string>()
  const voices = body['voices'].map((entry: unknown): VoiceOption => {
    if (!record(entry) || typeof entry['id'] !== 'string' || !entry['id'].trim() ||
      typeof entry['label'] !== 'string' || !entry['label'].trim() ||
      (entry['mode'] !== 'live' && entry['mode'] !== 'mock' && entry['mode'] !== 'local') ||
      seen.has(entry['id'])) throw new Error('Invalid voice')
    seen.add(entry['id'])
    return { id: entry['id'], label: entry['mode'] === 'mock' ? 'Demo voice' : entry['label'], mode: entry['mode'] }
  })
  if (!seen.has('default')) throw new Error('Missing default voice')
  return voices
}

export interface Experience {
  bargeInEnabled: boolean
  microphoneAutoGain: boolean
  character: Character
  appearance: Character
  voiceId: string
  quality: 'auto' | 'high' | 'low'
}
export function parseExperience(body: unknown): Experience {
  const characters = parseCharacters(body)
  if (!record(body) || !record(body['experience'])) throw new Error('Missing experience configuration')
  const config = body['experience']
  const character = characters.find((entry) => entry.id === config['character_id'])
  const appearance = characters.find((entry) => entry.id === config['appearance_id'])
  const voiceId = config['voice_id']
  const quality = config['quality']
  const bargeInEnabled = config['barge_in_enabled']
  const microphoneAutoGain = config['microphone_auto_gain']
  if (typeof bargeInEnabled !== 'boolean' || typeof microphoneAutoGain !== 'boolean' || !character || !appearance || typeof voiceId !== 'string' || !voiceId ||
      (quality !== 'auto' && quality !== 'high' && quality !== 'low') ||
      (character.avatar.renderer === 'vrm' && appearance.avatar.renderer !== 'vrm')) {
    throw new Error('Invalid experience configuration')
  }
  return { character, appearance, voiceId, quality, bargeInEnabled, microphoneAutoGain }
}
