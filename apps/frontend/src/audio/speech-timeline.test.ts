import { describe, expect, it } from 'vitest'
import { SpeechTimeline } from './speech-timeline'

describe('speech timing', () => {
  it('follows scheduled chunks across a network stall, then cancels all cues', () => {
    const timeline = new SpeechTimeline()
    timeline.begin('one')
    timeline.add('one', [{ start: 0.1, end: 0.4, value: 'aa', weight: 1 }])
    timeline.schedule(0, 0.2, 10)
    timeline.schedule(0.2, 0.4, 11)
    expect(timeline.sample(10.15)?.aa).toBeGreaterThan(0)
    expect(timeline.sample(10.5)).toBeNull()
    expect(timeline.sample(11.05)?.aa).toBeGreaterThan(0)
    timeline.clear()
    expect(timeline.sample(11.05)).toBeNull()
  })
  it('ignores alignment from a cancelled utterance', () => {
    const timeline = new SpeechTimeline()
    timeline.begin('new')
    timeline.add('old', [{ start: 0, end: 1, value: 'aa', weight: 1 }])
    timeline.schedule(0, 1, 0)
    expect(timeline.sample(0.5)).toBeNull()
  })
})
