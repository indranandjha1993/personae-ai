/**
 * Maps the backend's character vocabulary onto VRM expression weights.
 * An unmapped cue degrades to neutral rather than throwing.
 */

/** VRM 1.0 emotion presets. */
export type VrmEmotion = 'neutral' | 'happy' | 'angry' | 'sad' | 'relaxed' | 'surprised'

/** VRM 1.0 viseme presets, driven by audio amplitude rather than phonemes. */
export const VISEMES = ['aa', 'ih', 'ou', 'ee', 'oh'] as const

/**
 * What the character is doing, independent of what it says. Without this it
 * only reacts once a reply lands, so the wait reads as a freeze.
 */
export type Activity = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error'

export interface ActivityPose {
  /** Radians the head tilts; positive looks up, negative looks down. */
  headPitch: number
  /** Radians the head turns aside, as when thinking. */
  headYaw: number
  /** How much the body leans in. */
  lean: number
  /** Blink interval multiplier; lower blinks more often. */
  blinkRate: number
  /** Idle sway amplitude, so attention reads as stillness. */
  sway: number
}

export const ACTIVITY_POSE: Record<Activity, ActivityPose> = {
  // Relaxed, gently moving.
  idle: { headPitch: 0, headYaw: 0, lean: 0, blinkRate: 1, sway: 1 },
  // Attentive: head up and slightly forward, very still.
  listening: { headPitch: -0.06, headYaw: 0, lean: 0.09, blinkRate: 1.4, sway: 0.35 },
  // Considering: eyes off to one side, head tipped, almost motionless.
  thinking: { headPitch: 0.13, headYaw: 0.26, lean: -0.05, blinkRate: 0.55, sway: 0.5 },
  // Engaged while talking.
  speaking: { headPitch: -0.03, headYaw: 0, lean: 0.05, blinkRate: 1, sway: 0.8 },
  error: { headPitch: 0.08, headYaw: 0, lean: -0.04, blinkRate: 1, sway: 0.6 },
}

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
 * Playback loudness as a mouth-open weight. No provider emits viseme events,
 * so amplitude drives the mouth -- which cannot drift out of sync.
 */
export function mouthOpenness(rms: number): number {
  // Speech RMS sits well below full scale, so a modest ceiling keeps the mouth
  // expressive instead of barely moving.
  const normalised = Math.min(1, rms / 0.18)
  // Ease so quiet passages still register without the mouth flapping wide.
  return Math.min(1, normalised ** 0.6)
}

