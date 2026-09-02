/**
 * Whether her words are on screen yet.
 *
 * The reply text arrives before the first audio chunk, so "not speaking" is
 * true during the pause before she starts talking. Gating on that alone shows
 * the whole line seconds early, which is the spoiler the gate exists to stop.
 */
export function visibleCaption(
  reply: string,
  spoken: boolean,
  liveCaptions: boolean,
): string {
  if (reply === '') return ''
  return liveCaptions || spoken ? reply : ''
}
