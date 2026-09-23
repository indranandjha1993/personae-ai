/** Cues use source-audio time; each scheduled chunk maps it to the audio clock. */
export type MouthChannel = 'aa' | 'ih' | 'ou' | 'ee' | 'oh' | 'closed'
export type MouthWeights = Record<MouthChannel, number>
export interface VisemeCue { start: number; end: number; value: MouthChannel; weight: number }
export interface CharacterCue { start: number; end: number; text: string }
interface Utterance {
  id: string
  cues: VisemeCue[]
  chunks: { start: number; end: number; clock: number }[]
}

export class SpeechTimeline {
  private utterances: Utterance[] = []
  private current: Utterance | null = null

  begin(id: string): void {
    this.current = { id, cues: [], chunks: [] }
    this.utterances.push(this.current)
    // A stalled playback queue must not grow facial metadata indefinitely.
    if (this.utterances.length > 128) this.utterances.shift()
  }

  add(id: string, cues: VisemeCue[]): void {
    const utterance = this.utterances.find((item) => item.id === id)
    if (utterance) utterance.cues.push(...cues.slice(0, 4096 - utterance.cues.length))
  }

  schedule(start: number, end: number, clock: number): void {
    this.current?.chunks.push({ start, end, clock })
  }

  sample(now: number): MouthWeights | null {
    let result: MouthWeights | null = null
    for (const utterance of this.utterances) {
      for (const chunk of utterance.chunks) {
        if (now < chunk.clock || now >= chunk.clock + chunk.end - chunk.start) continue
        const time = chunk.start + now - chunk.clock
        for (const cue of utterance.cues) {
          if (time < cue.start || time >= cue.end) continue
          result ??= { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0, closed: 0 }
          // Smooth 25ms edges; overlapping cues blend (coarticulation).
          const envelope = Math.min(1, (time - cue.start) / 0.025, (cue.end - time) / 0.025)
          result[cue.value] = Math.max(result[cue.value], cue.weight * Math.max(0, envelope))
        }
      }
    }
    // Retire completed utterances; retain current since more chunks may arrive.
    this.utterances = this.utterances.filter((item) => item === this.current ||
      item.chunks.some((chunk) => chunk.clock + chunk.end - chunk.start > now))
    return result
  }

  clear(): void { this.utterances = []; this.current = null }
}
