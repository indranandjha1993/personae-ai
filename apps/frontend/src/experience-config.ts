/** Validated deployment-owned character and conversation configuration. */
import { parseAvatar, type AvatarConfig } from './avatar/config'

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

export interface Experience {
  allowVoiceInterruption: boolean
  microphoneAutoVolume: boolean
  character: Character
  appearance: Character
  quality: 'auto' | 'high' | 'low'
}
export function parseExperience(body: unknown): Experience {
  const characters = parseCharacters(body)
  if (!record(body) || !record(body['experience'])) throw new Error('Missing experience configuration')
  const config = body['experience']
  const character = characters.find((entry) => entry.id === config['character_id'])
  const appearance = characters.find((entry) => entry.id === config['appearance_id'])
  const quality = config['quality']
  const allowVoiceInterruption = config['allow_voice_interruption']
  const microphoneAutoVolume = config['microphone_auto_volume']
  if (typeof allowVoiceInterruption !== 'boolean' || typeof microphoneAutoVolume !== 'boolean' || !character || !appearance ||
      (quality !== 'auto' && quality !== 'high' && quality !== 'low') ||
      (character.avatar.renderer === 'vrm' && appearance.avatar.renderer !== 'vrm')) {
    throw new Error('Invalid experience configuration')
  }
  return { character, appearance, quality, allowVoiceInterruption, microphoneAutoVolume }
}
