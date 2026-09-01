/**
 * The 3D character.
 *
 * Per-frame work happens inside useFrame and mutates refs directly. Driving it
 * through React state would re-render at 60fps and change nothing on screen,
 * so cues arrive as props and everything continuous stays out of React.
 */

import { useFrame } from '@react-three/fiber'
import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import { mouthOpenness, toPose, toVrmEmotion } from './expression-map'

/** Frame-rate independent smoothing; higher converges faster. */
const SMOOTHING = 9

/** Radians the upper arms rest below horizontal, out of the loaded T-pose. */
const ARM_REST = 1.25

/** How much each emotion opens or closes the posture, when blendshapes are absent. */
const EMOTION_POSTURE: Record<string, number> = {
  happy: 1,
  surprised: 0.8,
  relaxed: 0.3,
  neutral: 0,
  angry: -0.4,
  sad: -1,
}

export interface AvatarProps {
  modelUrl: string
  gesture: string
  emotion: string
  /** Returns current playback loudness, 0 when silent. */
  loudness: () => number
  onError: (message: string) => void
  /** Reports the loaded model's real bounds so the camera can frame it. */
  onFramed: (bounds: { headY: number; height: number; floorY: number }) => void
}

export function Avatar({
  modelUrl,
  gesture,
  emotion,
  loudness,
  onError,
  onFramed,
}: AvatarProps) {
  const [vrm, setVrm] = useState<VRM | null>(null)
  const current = useRef({ armSwing: 0, headTilt: 0, torsoTwist: 0, mouth: 0 })
  const clock = useRef(0)

  useEffect(() => {
    let cancelled = false
    const loader = new GLTFLoader()
    loader.register((parser) => new VRMLoaderPlugin(parser))

    loader.loadAsync(modelUrl).then(
      (gltf) => {
        if (cancelled) return
        const loaded = gltf.userData['vrm'] as VRM | undefined
        if (!loaded) {
          onError('That file loaded but is not a VRM model.')
          return
        }
        // Removing unused vertices and joints measurably improves frame time.
        VRMUtils.removeUnnecessaryVertices(loaded.scene)
        VRMUtils.combineSkeletons(loaded.scene)
        loaded.scene.rotation.y = Math.PI // face the camera

        // Models differ in height and origin, so frame from the real bounds
        // rather than assuming: aim at the head and pull back to fit the torso.
        const box = new THREE.Box3().setFromObject(loaded.scene)
        const height = box.max.y - box.min.y
        const headY = box.max.y
        onFramed({ headY, height, floorY: box.min.y })
        setVrm(loaded)
      },
      () => {
        if (!cancelled) onError('Could not load the avatar model.')
      },
    )

    return () => {
      cancelled = true
    }
  }, [modelUrl, onError, onFramed])

  useEffect(() => {
    return () => {
      if (vrm) VRMUtils.deepDispose(vrm.scene)
    }
  }, [vrm])

  useFrame((_, delta) => {
    if (!vrm) return
    clock.current += delta

    const target = toPose(gesture)
    const state = current.current
    const damp = THREE.MathUtils.damp
    const vrmEmotion = toVrmEmotion(emotion)
    // Emotion is also expressed as posture, so it still reads on models with no
    // emotion blendshapes: lifted and open when positive, closed and lowered
    // when negative.
    const lift = EMOTION_POSTURE[vrmEmotion] ?? 0

    state.armSwing = damp(state.armSwing, target.armSwing, SMOOTHING, delta)
    state.headTilt = damp(state.headTilt, target.headTilt, SMOOTHING, delta)
    state.torsoTwist = damp(state.torsoTwist, target.torsoTwist, SMOOTHING, delta)
    // The mouth chases loudness faster than the body moves, or speech looks dubbed.
    state.mouth = damp(state.mouth, mouthOpenness(loudness()), SMOOTHING * 2.2, delta)

    const humanoid = vrm.humanoid
    const breath = Math.sin(clock.current * 1.6) * 0.02

    // A VRM loads in T-pose with the arms straight out. Roughly 70 degrees of
    // downward rotation gives a natural rest; gestures move from there.
    const leftArm = humanoid.getNormalizedBoneNode('leftUpperArm')
    const rightArm = humanoid.getNormalizedBoneNode('rightUpperArm')
    if (leftArm) {
      leftArm.rotation.z = ARM_REST - state.armSwing - lift * 0.12
      leftArm.rotation.x = state.armSwing * 0.35
    }
    if (rightArm) {
      rightArm.rotation.z = -ARM_REST + state.armSwing + lift * 0.12
      rightArm.rotation.x = state.armSwing * 0.35
    }

    // Bending the forearms keeps the silhouette from reading as a mannequin.
    const leftLower = humanoid.getNormalizedBoneNode('leftLowerArm')
    const rightLower = humanoid.getNormalizedBoneNode('rightLowerArm')
    if (leftLower) leftLower.rotation.y = -0.3 - state.armSwing * 0.5
    if (rightLower) rightLower.rotation.y = 0.3 + state.armSwing * 0.5

    const head = humanoid.getNormalizedBoneNode('head')
    if (head) {
      head.rotation.x = state.headTilt + breath * 0.5 - lift * 0.12
      head.rotation.y = state.torsoTwist * 0.6
    }

    const spine = humanoid.getNormalizedBoneNode('spine')
    if (spine) {
      spine.rotation.y = state.torsoTwist
      spine.rotation.x = breath - lift * 0.06
    }

    const expressions = vrm.expressionManager
    if (expressions) {
      // 'aa' is the open-vowel viseme; amplitude cannot tell us which vowel,
      // so one well-timed shape reads better than guessing between five.
      expressions.setValue('aa', state.mouth)

      // Many models -- including most VRM 0.x avatars -- ship visemes but no
      // emotion presets. Setting a missing one is silently ignored, so posture
      // below carries the emotion for those models.
      for (const preset of ['happy', 'angry', 'sad', 'relaxed', 'surprised'] as const) {
        expressions.setValue(preset, preset === vrmEmotion ? 0.85 : 0)
      }
    }

    vrm.update(delta)
  })

  return vrm ? <primitive object={vrm.scene} /> : null
}
