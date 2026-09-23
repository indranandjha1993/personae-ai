/** Own the browser resources for one conversation attempt, including stale starts. */
import type { Capture } from './audio/capture'
import type { PcmPlayer } from './audio/playback'
import type { Session } from './conversation-socket'

export class ConversationResources {
  capture: Capture | null = null
  session: Session | null = null
  player: PcmPlayer | null = null
  context: AudioContext | null = null
  starting = false
  private generation = 0

  begin(): number | null {
    if (this.starting || this.session) return null
    this.starting = true
    return ++this.generation
  }

  isCurrent(generation: number): boolean {
    return this.generation === generation
  }

  release(): void {
    // Invalidate callbacks before closing resources; close can dispatch events.
    this.generation += 1
    this.starting = false
    const { capture, session, player, context } = this
    this.capture = null
    this.session = null
    this.player = null
    this.context = null
    // A failed device cleanup must not leak the remaining resources.
    for (const close of [
      () => capture?.stop(),
      () => session?.close(),
      () => player?.stop(),
      () => { void context?.close().catch(() => {}) },
    ]) {
      try { close() } catch { /* Continue releasing the other resources. */ }
    }
  }
}
