/**
 * Whether her words are on screen yet, and how much of them.
 *
 * Sentences are revealed once their audio has played, so with captions on the
 * text grows in step with her voice. The full reply arrives over the socket
 * long before she has finished saying it, so it is only substituted at the end
 * -- it is the cleaned, punctuated version of the same words.
 *
 * With captions off it waits for the turn to finish: the point of the toggle
 * is to hear the line before reading it, and a caption that keeps pace still
 * gives it away.
 */
export function visibleCaption(
  spokenSoFar: string,
  fullReply: string,
  turnFinished: boolean,
  liveCaptions: boolean,
): string {
  if (liveCaptions && !turnFinished) return spokenSoFar
  if (!liveCaptions && !turnFinished) return ''
  // A turn cut short by a barge-in, or ended by an error, never delivers the
  // full text -- what she managed to say is all there is to show.
  return fullReply !== '' ? fullReply : spokenSoFar
}
