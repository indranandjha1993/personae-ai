/**
 * Applies a body pose to the VRM skeleton.
 *
 * The model binds with its arms raised over the head rather than in a T-pose,
 * so every arm angle here is measured from a corrected rest: the roll that
 * brings the arms down to the sides is added on top of the pose, not baked
 * into it. Without that correction a "hands at rest" pose points straight up.
 */

import type * as THREE from 'three'
import type { VRM, VRMHumanBoneName } from '@pixiv/three-vrm'

import type { ArmPose, BodyPose, Motion } from './gestures'

/**
 * Roll that brings this model's arms from its raised bind pose down to the
 * sides. Measured from the model: the hands bind above the head.
 */
const ARM_DOWN_ROLL = 1.45

/** Finger joints, in the order a curl travels down the hand. */
const FINGERS = ['Index', 'Middle', 'Ring', 'Little'] as const
const JOINTS = ['Proximal', 'Intermediate', 'Distal'] as const

/** How far each joint folds relative to the curl amount. */
const JOINT_CURL = { Proximal: 1, Intermediate: 1.15, Distal: 0.75 }

/**
 * Which local axis a finger folds about, and how far a full curl travels.
 *
 * VRM normalised finger bones fold about z, with the sign following the hand.
 * The magnitude is deliberately modest: a fully closed fist on a stylised
 * model reads as a lump, and these hands are seen at conversational distance.
 */
const fingerAxis = 'z' as const
const FINGER_BEND = 0.9

type Side = 'left' | 'right'

function boneName(side: Side, part: string): VRMHumanBoneName {
  // Every name built here is a real humanoid bone; the cast keeps the joint
  // tables readable rather than spelling out fifty literal names.
  return (side + part.charAt(0).toUpperCase() + part.slice(1)) as VRMHumanBoneName
}

/** Apply one arm, from shoulder to fingertips. */
function applyArm(vrm: VRM, side: Side, pose: ArmPose, shoulderLift: number): void {
  const sign = side === 'left' ? -1 : 1
  const bone = (part: string): THREE.Object3D | null =>
    vrm.humanoid.getNormalizedBoneNode(boneName(side, part))

  const shoulder = bone('shoulder')
  if (shoulder) shoulder.rotation.z = sign * shoulderLift * 0.5

  const upper = bone('upperArm')
  if (upper) {
    // z carries the arm's height at the side; x swings it forward.
    upper.rotation.z = sign * (ARM_DOWN_ROLL - pose.upperOut)
    upper.rotation.x = -pose.upperForward
    upper.rotation.y = sign * pose.upperTwist
  }

  const lower = bone('lowerArm')
  // Elbows fold one way only, so the sign follows the side rather than the
  // value: a negative bend here would break the arm backwards.
  if (lower) lower.rotation.y = sign * pose.elbow

  const hand = bone('hand')
  if (hand) hand.rotation.z = sign * pose.wrist

  // Fingers curl about the model's own bend axis. Which axis that is has to
  // be read from the rig rather than assumed: on this model the normalised
  // bones inherit the bind rotation, so a guessed axis splays the hand into a
  // claw instead of closing it.
  for (const finger of FINGERS) {
    for (const joint of JOINTS) {
      const node = bone(`${finger}${joint}`)
      if (!node) continue
      node.rotation.set(0, 0, 0)
      node.rotation[fingerAxis] = sign * pose.curl * JOINT_CURL[joint] * FINGER_BEND
    }
  }

  // The thumb opposes the fingers, so it bends less and on its own axis.
  for (const joint of ['Metacarpal', 'Proximal', 'Distal'] as const) {
    const node = bone(`thumb${joint}`)
    if (node) {
      node.rotation.set(0, 0, 0)
      node.rotation[fingerAxis] = sign * pose.curl * 0.4 * FINGER_BEND
    }
  }
}

/**
 * Pose the upper body.
 *
 * Additive contributions -- breathing, emphasis, gaze -- are applied by the
 * caller afterwards, so this only writes the joints a gesture owns.
 */
export function applyBodyPose(vrm: VRM, pose: BodyPose): void {
  applyArm(vrm, 'left', pose.left, pose.shoulderLift)
  applyArm(vrm, 'right', pose.right, pose.shoulderLift)
}

/**
 * Play a motion, additively, on top of the already-applied pose.
 *
 * `seconds` counts from when the gesture began. Each motion runs a few cycles
 * and dies away on its own -- people nod twice and stop, they do not
 * metronome until the sentence ends.
 */
export function applyMotion(vrm: VRM, motion: Motion, seconds: number): void {
  // Two-ish visible cycles, then gone.
  const envelope = Math.exp(-seconds * 1.1)
  if (envelope < 0.01) return

  switch (motion) {
    case 'nod': {
      const head = vrm.humanoid.getNormalizedBoneNode('head')
      if (head) head.rotation.x += Math.sin(seconds * 2 * Math.PI * 1.7) * 0.12 * envelope
      break
    }
    case 'shake': {
      const head = vrm.humanoid.getNormalizedBoneNode('head')
      if (head) head.rotation.y += Math.sin(seconds * 2 * Math.PI * 2.1) * 0.15 * envelope
      break
    }
    case 'wave': {
      // The forearm pivots at the elbow, which is how a real wave moves.
      const forearm = vrm.humanoid.getNormalizedBoneNode('rightLowerArm')
      if (forearm) forearm.rotation.y += Math.sin(seconds * 2 * Math.PI * 2.3) * 0.28 * envelope
      break
    }
  }
}

/**
 * A beat: the small flick of the leading hand on a stressed word while a
 * gesture is held. Additive, on top of the pose, and gone within a quarter
 * of a second.
 */
export function applyBeat(vrm: VRM, amount: number): void {
  if (amount <= 0) return
  const forearm = vrm.humanoid.getNormalizedBoneNode('rightLowerArm')
  if (forearm) forearm.rotation.y += amount * 0.09
  const hand = vrm.humanoid.getNormalizedBoneNode('rightHand')
  if (hand) hand.rotation.z += amount * 0.14
}

/** The roll that returns this model's arms to its sides, for callers that need it. */
export { ARM_DOWN_ROLL }
