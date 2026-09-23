import type { AvatarConfig } from './config'

/** The hosted Epic player owns microphone, conversation audio and WebRTC A/V.
 * Keeping one clock avoids playing local PCM ahead of remote video.
 * The deployment must implement the Personae bridge described in docs/rendering.md.
 */
export function PixelStreamingStage({ avatar, characterId }: {
  avatar: AvatarConfig; characterId: string
}) {
  if (!avatar.player_url) return <p role="alert">Streaming player is not configured.</p>
  const url = new URL(avatar.player_url, window.location.href)
  url.searchParams.set('character', characterId)
  return <iframe title="Live avatar" src={url.href} className="pixel-player"
    allow="autoplay; microphone; fullscreen" referrerPolicy="no-referrer" />
}
