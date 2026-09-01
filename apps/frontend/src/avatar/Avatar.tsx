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

export interface AvatarProps {
  modelUrl: string
  gesture: string
  emotion: string
  /** Returns current playback loudness, 0 when silent. */
  loudness: () => number
  onError: (message: string) => void
}

export function Avatar({ modelUrl, gesture, emotion, loudness, onError }: AvatarProps) {
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
        setVrm(loaded)
      },
      () => {
        if (!cancelled) onError('Could not load the avatar model.')
      },
    )

    return () => {
      cancelled = true
    }
  }, [modelUrl, onError])

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

    state.armSwing = damp(state.armSwing, target.armSwing, SMOOTHING, delta)
    state.headTilt = damp(state.headTilt, target.headTilt, SMOOTHING, delta)
    state.torsoTwist = damp(state.torsoTwist, target.torsoTwist, SMOOTHING, delta)
    // The mouth chases loudness faster than the body moves, or speech looks dubbed.
    state.mouth = damp(state.mouth, mouthOpenness(loudness()), SMOOTHING * 2.2, delta)

    const humanoid = vrm.humanoid
    const breath = Math.sin(clock.current * 1.6) * 0.02

    const leftArm = humanoid.getNormalizedBoneNode('leftUpperArm')
    const rightArm = humanoid.getNormalizedBoneNode('rightUpperArm')
    if (leftArm) leftArm.rotation.z = 1.2 - state.armSwing
    if (rightArm) rightArm.rotation.z = -1.2 + state.armSwing

    const head = humanoid.getNormalizedBoneNode('head')
    if (head) {
      head.rotation.x = state.headTilt + breath * 0.5
      head.rotation.y = state.torsoTwist * 0.6
    }

    const spine = humanoid.getNormalizedBoneNode('spine')
    if (spine) {
      spine.rotation.y = state.torsoTwist
      spine.rotation.x = breath
    }

    const expressions = vrm.expressionManager
    if (expressions) {
      // 'aa' is the open-vowel viseme; amplitude cannot tell us which vowel,
      // so one well-timed shape reads better than guessing between five.
      expressions.setValue('aa', state.mouth)
      for (const preset of ['happy', 'angry', 'sad', 'relaxed', 'surprised'] as const) {
        expressions.setValue(preset, preset === toVrmEmotion(emotion) ? 0.85 : 0)
      }
    }

    vrm.update(delta)
  })

  return vrm ? <primitive object={vrm.scene} /> : null
}
