/**
 * Authored motion for the gestures she marks.
 *
 * A held pose can put a hand where a wave belongs; it cannot make the wave.
 * Where a VRM Animation clip exists for a gesture it plays over the arms, and
 * the procedural rig keeps the head, breath and face. Clips are optional and
 * not shipped: they are listed in a manifest beside the files, and a gesture
 * without one stays procedural.
 */

import type { VRM, VRMHumanBoneName } from '@pixiv/three-vrm'
import {
  createVRMAnimationClip,
  VRMAnimationLoaderPlugin,
  type VRMAnimation,
} from '@pixiv/three-vrm-animation'
import type * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

/** Where the manifest lives; clip paths inside it are relative to this. */
export const MANIFEST_URL = '/motions/index.json'

/** Gesture name to clip file, for the gestures that have one. */
export type MotionManifest = Record<string, string>

/** Narrow a fetched manifest: only known-shaped names and .vrma files count. */
export function parseManifest(raw: unknown): MotionManifest {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return {}
  const manifest: MotionManifest = {}
  for (const [gesture, file] of Object.entries(raw)) {
    if (
      typeof file === 'string' &&
      /^[\w.-]+\.vrma$/i.test(file) &&
      /^(?:idle|gesture-[a-z-]+)$/.test(gesture)
    ) {
      manifest[gesture] = file
    }
  }
  return manifest
}

const SIDES = ['left', 'right'] as const
const FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Little'] as const
const JOINTS = ['Metacarpal', 'Proximal', 'Intermediate', 'Distal'] as const

/** The humanoid bones a clip may drive: shoulders to fingertips, nothing else. */
export const ARM_BONES: readonly VRMHumanBoneName[] = SIDES.flatMap((side) => [
  `${side}Shoulder` as const,
  `${side}UpperArm` as const,
  `${side}LowerArm` as const,
  `${side}Hand` as const,
  ...FINGERS.flatMap((finger) =>
    JOINTS.map((joint) => `${side}${finger}${joint}` as VRMHumanBoneName),
  ),
])

/** The scene-graph names of this model's arm bones, as clip tracks address them. */
export function armNodeNames(vrm: VRM): Set<string> {
  const names = new Set<string>()
  for (const bone of ARM_BONES) {
    const node = vrm.humanoid.getNormalizedBoneNode(bone)
    if (node) names.add(node.name)
  }
  return names
}

/**
 * Keep only the tracks that move the arms.
 *
 * A clip authored for a whole body would otherwise fight the procedural head
 * and torso, and its face tracks would overwrite the lip sync.
 */
export function armTracksOnly<T extends { name: string }>(tracks: readonly T[], arms: Set<string>): T[] {
  return tracks.filter((track) => arms.has(track.name.slice(0, track.name.lastIndexOf('.'))))
}

/**
 * Load every clip the manifest names, keyed by gesture.
 *
 * A missing manifest, a missing file, or a clip that turns out to drive no
 * arm bones simply leaves that gesture procedural; nothing here can fail the
 * avatar.
 */
export async function loadMotions(
  vrm: VRM,
  manifestUrl: string = MANIFEST_URL,
): Promise<Map<string, THREE.AnimationClip>> {
  const clips = new Map<string, THREE.AnimationClip>()

  let manifest: MotionManifest
  try {
    const response = await fetch(manifestUrl)
    if (!response.ok) return clips
    manifest = parseManifest(await response.json())
  } catch {
    return clips
  }

  const loader = new GLTFLoader()
  loader.register((parser) => new VRMAnimationLoaderPlugin(parser))
  const base = manifestUrl.slice(0, manifestUrl.lastIndexOf('/') + 1)
  const arms = armNodeNames(vrm)

  await Promise.all(
    Object.entries(manifest).map(async ([gesture, file]) => {
      try {
        const gltf = await loader.loadAsync(base + file)
        const animations = gltf.userData['vrmAnimations'] as VRMAnimation[] | undefined
        const first = animations?.[0]
        if (!first) return
        const clip = createVRMAnimationClip(first, vrm)
        clip.tracks = armTracksOnly(clip.tracks, arms)
        clip.resetDuration()
        if (clip.tracks.length > 0) clips.set(gesture, clip)
      } catch {
        // A broken or absent clip leaves that gesture to the procedural rig.
      }
    }),
  )
  return clips
}
