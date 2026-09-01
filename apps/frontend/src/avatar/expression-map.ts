/**
 * Translates the backend's character vocabulary into VRM expression weights.
 *
 * The backend emits cues drawn from each character's declared vocabulary; VRM
 * defines a fixed set of preset expressions. This is the seam between the two,
 * kept as data so an unmapped cue degrades to neutral rather than throwing.
 */

/** VRM 1.0 emotion presets. */
export type VrmEmotion = 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised'

/** VRM 1.0 viseme presets, driven by audio amplitude rather than phonemes. */
export const VISEMES = ['aa', 'ih', 'ou', 'ee', 'oh'] as const

const EMOTION_TO_VRM: Record<string, VrmEmotion> = {
  neutral: 'neutral',
  amused: 'happy',
  delighted: 'happy',
  focused: 'relaxed',
  solemn: 'sad',
  indignant: 'angry',
  impatient: 'angry',
  annoyed: 'angry',
  wry: 'happy',
  alert: 'surprised',
  unimpressed: 'sad',
}

export interface Pose {
  /** Radians. Positive lifts the arms forward. */
  armSwing: number
  /** Radians. Positive tilts the head back. */
  headTilt: number
  /** Radians. Rotation of the upper body. */
  torsoTwist: number
}

const RESTING: Pose = { armSwing: 0, headTilt: 0, torsoTwist: 0 }

const GESTURE_TO_POSE: Record<string, Pose> = {
  idle: RESTING,
  'gesture-explain': { armSwing: 0.55, headTilt: 0.05, torsoTwist: 0.08 },
  'gesture-point': { armSwing: 0.9, headTilt: -0.08, torsoTwist: 0.22 },
  'gesture-dismiss': { armSwing: 0.35, headTilt: 0.12, torsoTwist: -0.2 },
  'gesture-declaim': { armSwing: 1.05, headTilt: -0.18, torsoTwist: 0 },
  'gesture-welcome': { armSwing: 0.75, headTilt: -0.05, torsoTwist: 0 },
  'gesture-summon': { armSwing: 0.85, headTilt: -0.1, torsoTwist: 0.14 },
  'gesture-consider': { armSwing: 0.2, headTilt: 0.16, torsoTwist: -0.1 },
  'gesture-indicate': { armSwing: 0.5, headTilt: 0, torsoTwist: 0.16 },
}

/** Map a character emotion cue to a VRM preset, defaulting to neutral. */
export function toVrmEmotion(emotion: string): VrmEmotion {
  return EMOTION_TO_VRM[emotion] ?? 'neutral'
}

/** Map a character gesture cue to a target pose, defaulting to rest. */
export function toPose(gesture: string): Pose {
  return GESTURE_TO_POSE[gesture] ?? RESTING
}

/**
 * Convert playback loudness into a mouth-open weight.
 *
 * Neither Deepgram nor a chat model emits viseme events, so the mouth is driven
 * by the amplitude of what is actually playing. That is sample-accurate by
 * construction: the mouth cannot drift out of sync with the audio.
 */
export function mouthOpenness(rms: number): number {
  // Speech RMS sits well below full scale, so a modest ceiling keeps the mouth
  // expressive instead of barely moving.
  const normalised = Math.min(1, rms / 0.18)
  // Ease so quiet passages still register without the mouth flapping wide.
  return Math.min(1, normalised ** 0.6)
}
