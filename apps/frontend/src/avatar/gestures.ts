/**
 * Arm, hand and torso poses for conversational gesture.
 *
 * A gesture is a target angle per joint rather than one number for both arms:
 * people gesture asymmetrically, and a pose that moves the two arms together
 * reads as a puppet. Angles are in radians on the VRM normalised rig, where
 * the model's own bind pose has already been corrected to arms-at-rest.
 *
 * Only the upper body is described. The camera frames head to waist, so legs
 * are never in shot and are left to the model's own rest pose.
 */

/** One arm, shoulder to fingertips. */
export interface ArmPose {
  /** Raises the arm forward from the side. */
  upperForward: number
  /** Lifts the arm away from the body. */
  upperOut: number
  /** Rotation about the arm's own axis, which turns the palm. */
  upperTwist: number
  /** Elbow bend; always positive, since elbows only fold one way. */
  elbow: number
  /** Wrist angle, which is most of what reads as a hand "speaking". */
  wrist: number
  /** How closed the fingers are: 0 open and relaxed, 1 a fist. */
  curl: number
  /**
   * Spreads the fingers apart, for an open presenting palm.
   *
   * Carried through the vocabulary but not yet applied: the axis a finger
   * abducts about differs from the one it folds about, and posing it on a
   * guess splays the hand.
   */
  spread: number
}

/**
 * A repeating movement layered over the held pose.
 *
 * A nod, a head-shake, or a wave is not a position but an oscillation: it
 * plays a couple of cycles when the gesture lands and dies away on its own.
 */
export type Motion = 'nod' | 'shake' | 'wave'

export interface BodyPose {
  left: ArmPose
  right: ArmPose
  /** Movement that plays when the gesture begins, if any. */
  motion?: Motion
  /** Rotation of the upper body about the vertical. */
  torsoTwist: number
  /** Forward lean from the waist. */
  torsoLean: number
  /** Shoulders rising, as in a shrug. */
  shoulderLift: number
  /** Head angles that belong to the gesture rather than to the mood. */
  headTilt: number
}

/**
 * Hands resting: arms down, elbows very slightly bent, fingers loose.
 *
 * A perfectly straight arm with splayed fingers is the single strongest
 * "mannequin" cue, so even rest carries a little bend and curl.
 */
const REST_ARM: ArmPose = {
  upperForward: 0.04,
  upperOut: -0.06,
  upperTwist: 0,
  elbow: 0.18,
  wrist: 0,
  curl: 0.22,
  spread: 0.1,
}

function arm(overrides: Partial<ArmPose>): ArmPose {
  return { ...REST_ARM, ...overrides }
}

export const REST: BodyPose = {
  left: REST_ARM,
  right: REST_ARM,
  torsoTwist: 0,
  torsoLean: 0,
  shoulderLift: 0,
  headTilt: 0,
}

function body(overrides: Partial<BodyPose>): BodyPose {
  return { ...REST, ...overrides }
}

/**
 * The gesture vocabulary.
 *
 * Each is built around one dominant hand, with the other doing less: matched
 * arms read as theatrical, and real speakers lead with one side.
 */
const GESTURES: Record<string, BodyPose> = {
  idle: REST,

  // Both palms up and open, the everyday "here's the thing" of explanation.
  'gesture-explain': body({
    left: arm({ upperForward: 0.5, upperOut: 0.3, elbow: 1.15, wrist: -0.2, curl: 0.1, spread: 0.4 }),
    right: arm({ upperForward: 0.42, upperOut: 0.26, elbow: 1.05, wrist: -0.16, curl: 0.12, spread: 0.35 }),
    torsoLean: 0.05,
  }),

  // One hand out toward the thing. An open hand rather than a curled one:
  // the rig folds all four fingers together, so a tight curl with the arm
  // raised reads as a thumbs-up, not a point.
  'gesture-point': body({
    right: arm({ upperForward: 0.85, upperOut: 0.16, elbow: 0.62, wrist: 0.1, curl: 0.18, spread: 0 }),
    left: arm({ upperForward: 0.1, elbow: 0.3 }),
    torsoTwist: -0.12,
    headTilt: -0.04,
  }),

  // A hand brushing the idea aside.
  'gesture-dismiss': body({
    right: arm({ upperForward: 0.3, upperOut: 0.45, upperTwist: 0.5, elbow: 0.9, wrist: 0.35, curl: 0.15, spread: 0.3 }),
    torsoTwist: -0.16,
    headTilt: 0.1,
  }),

  // Hand near the chin, weight settled back: visible thought.
  'gesture-consider': body({
    right: arm({ upperForward: 0.55, upperOut: 0.05, elbow: 2.0, wrist: -0.3, curl: 0.55, spread: 0 }),
    left: arm({ upperForward: 0.12, upperOut: 0.05, elbow: 0.7, curl: 0.3 }),
    torsoLean: -0.05,
    headTilt: 0.14,
    torsoTwist: 0.08,
  }),

  // Arms opening outward in welcome.
  'gesture-welcome': body({
    left: arm({ upperForward: 0.45, upperOut: 0.55, upperTwist: -0.35, elbow: 0.75, wrist: -0.25, curl: 0.05, spread: 0.5 }),
    right: arm({ upperForward: 0.45, upperOut: 0.55, upperTwist: 0.35, elbow: 0.75, wrist: -0.25, curl: 0.05, spread: 0.5 }),
    torsoLean: 0.07,
    headTilt: -0.06,
  }),

  // Both hands raised, palms forward: emphasis, or holding a thought.
  'gesture-declaim': body({
    left: arm({ upperForward: 0.95, upperOut: 0.35, elbow: 0.85, wrist: -0.4, curl: 0.08, spread: 0.45 }),
    right: arm({ upperForward: 0.95, upperOut: 0.35, elbow: 0.85, wrist: -0.4, curl: 0.08, spread: 0.45 }),
    torsoLean: 0.04,
    headTilt: -0.12,
  }),

  // A small beckoning turn of one hand.
  'gesture-summon': body({
    right: arm({ upperForward: 0.6, upperOut: 0.2, upperTwist: -0.4, elbow: 1.3, wrist: -0.35, curl: 0.35, spread: 0.2 }),
    torsoTwist: -0.1,
  }),

  // Presenting one hand toward what is being described.
  'gesture-indicate': body({
    right: arm({ upperForward: 0.55, upperOut: 0.35, upperTwist: 0.45, elbow: 0.95, wrist: -0.3, curl: 0.06, spread: 0.45 }),
    left: arm({ upperForward: 0.12, elbow: 0.35 }),
    torsoTwist: -0.14,
  }),

  // Shoulders up, hands turned out: not knowing.
  'gesture-shrug': body({
    left: arm({ upperForward: 0.2, upperOut: 0.42, upperTwist: -0.6, elbow: 1.25, wrist: -0.45, curl: 0.1, spread: 0.4 }),
    right: arm({ upperForward: 0.2, upperOut: 0.42, upperTwist: 0.6, elbow: 1.25, wrist: -0.45, curl: 0.1, spread: 0.4 }),
    shoulderLift: 0.32,
    headTilt: 0.1,
  }),

  // A hand to the chest: sincerity, or speaking about oneself.
  'gesture-sincere': body({
    right: arm({ upperForward: 0.72, upperOut: -0.08, elbow: 1.75, wrist: -0.2, curl: 0.25, spread: 0.25 }),
    torsoLean: 0.06,
    headTilt: 0.05,
  }),

  // Fingers pinched: precision, a fine distinction.
  'gesture-precise': body({
    right: arm({ upperForward: 0.68, upperOut: 0.14, elbow: 1.45, wrist: -0.15, curl: 0.55, spread: 0.05 }),
    left: arm({ upperForward: 0.1, elbow: 0.3 }),
    torsoLean: 0.04,
    headTilt: -0.05,
  }),

  // Everyday agreement: a couple of nods, the body barely involved.
  'gesture-yes': body({
    motion: 'nod',
    headTilt: 0.02,
  }),

  // Everyday refusal: the head shakes while one palm turns out, the
  // hand half of saying no.
  'gesture-no': body({
    motion: 'shake',
    right: arm({ upperForward: 0.62, upperOut: 0.2, elbow: 1.15, wrist: -0.35, curl: 0.08, spread: 0.3 }),
  }),

  // A raised hand waving hello or goodbye, the forearm doing the moving.
  'gesture-wave': body({
    motion: 'wave',
    right: arm({ upperForward: 0.5, upperOut: 0.7, elbow: 1.5, wrist: 0, curl: 0.06, spread: 0.3 }),
    headTilt: -0.04,
  }),

  // Palms together at the chest with a small bow: a pranam, offered the way
  // it is in daily life rather than theatrically.
  'gesture-namaste': body({
    left: arm({ upperForward: 0.75, upperOut: -0.15, upperTwist: -0.3, elbow: 1.9, wrist: -0.15, curl: 0.02, spread: 0 }),
    right: arm({ upperForward: 0.75, upperOut: -0.15, upperTwist: 0.3, elbow: 1.9, wrist: -0.15, curl: 0.02, spread: 0 }),
    torsoLean: 0.06,
    headTilt: 0.16,
  }),

  // Palms down, settling: calm, or slowing something down.
  'gesture-settle': body({
    left: arm({ upperForward: 0.45, upperOut: 0.3, upperTwist: 0.7, elbow: 1.0, wrist: 0.3, curl: 0.1, spread: 0.35 }),
    right: arm({ upperForward: 0.45, upperOut: 0.3, upperTwist: -0.7, elbow: 1.0, wrist: 0.3, curl: 0.1, spread: 0.35 }),
    torsoLean: -0.03,
  }),
}

/** Every gesture the character vocabulary may name. */
export const GESTURE_NAMES = Object.keys(GESTURES)

/** Map a gesture cue to a full body pose, defaulting to rest. */
export function toBodyPose(gesture: string): BodyPose {
  return GESTURES[gesture] ?? REST
}

/** Blend between two poses, for easing from one gesture into the next. */
export function blendPoses(from: BodyPose, to: BodyPose, t: number): BodyPose {
  const mix = (a: number, b: number): number => a + (b - a) * t
  const mixArm = (a: ArmPose, b: ArmPose): ArmPose => ({
    upperForward: mix(a.upperForward, b.upperForward),
    upperOut: mix(a.upperOut, b.upperOut),
    upperTwist: mix(a.upperTwist, b.upperTwist),
    elbow: mix(a.elbow, b.elbow),
    wrist: mix(a.wrist, b.wrist),
    curl: mix(a.curl, b.curl),
    spread: mix(a.spread, b.spread),
  })
  return {
    left: mixArm(from.left, to.left),
    right: mixArm(from.right, to.right),
    torsoTwist: mix(from.torsoTwist, to.torsoTwist),
    torsoLean: mix(from.torsoLean, to.torsoLean),
    shoulderLift: mix(from.shoulderLift, to.shoulderLift),
    headTilt: mix(from.headTilt, to.headTilt),
  }
}
