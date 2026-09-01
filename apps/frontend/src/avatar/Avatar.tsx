/**
 * The VRM character.
 *
 * Setup follows the three-vrm basic example: the loader plugin, the three
 * VRMUtils optimisations, disabled frustum culling, and vrm.update() once per
 * frame. Per-frame values mutate refs rather than React state.
 */

import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { useFrame } from '@react-three/fiber'
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import {
  ACTIVITY_POSE,
  MOUTH_AT_REST,
  mouthOpenness,
  toPose,
  toVrmEmotion,
  type Activity,
} from './expression-map'

const SMOOTHING = 9

/** How far each emotion opens or closes the posture, for models without blendshapes. */
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
  activity: Activity
  loudness: () => number
  onError: (message: string) => void
  onFramed: (bounds: { headY: number; height: number }) => void
}

export function Avatar({
  modelUrl,
  gesture,
  emotion,
  activity,
  loudness,
  onError,
  onFramed,
}: AvatarProps) {
  const [vrm, setVrm] = useState<VRM | null>(null)
  const state = useRef({
    armSwing: 0,
    headTilt: 0,
    torsoTwist: 0,
    mouth: 0,
    pitch: 0,
    yaw: 0,
    lean: 0,
  })
  const clock = useRef(0)
  const nextBlink = useRef(2)
  const blink = useRef(0)

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

        VRMUtils.removeUnnecessaryVertices(gltf.scene)
        VRMUtils.combineSkeletons(gltf.scene)
        // Normalises VRM 0.x orientation; VRM 1.0 already faces the camera.
        VRMUtils.rotateVRM0(loaded)

        loaded.scene.traverse((object) => {
          // A close crop otherwise culls geometry whose bounding volume falls
          // outside the frustum.
          object.frustumCulled = false
          // Props and limbs that intrude on a portrait. Matching by name keeps
          // the clothing intact, which a bounds test does not.
          if (/robo|arm|hand/i.test(object.name)) object.visible = false
        })

        loaded.scene.updateMatrixWorld(true)
        const headNode = loaded.humanoid.getNormalizedBoneNode('head')
        const box = new THREE.Box3().setFromObject(loaded.scene)
        const headY = headNode
          ? new THREE.Vector3().setFromMatrixPosition(headNode.matrixWorld).y
          : box.max.y * 0.93
        onFramed({ headY, height: box.max.y - box.min.y })
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
    const s = state.current
    const damp = THREE.MathUtils.damp
    const vrmEmotion = toVrmEmotion(emotion)
    const pose = ACTIVITY_POSE[activity]
    const lift = EMOTION_POSTURE[vrmEmotion] ?? 0

    s.armSwing = damp(s.armSwing, target.armSwing, SMOOTHING, delta)
    s.headTilt = damp(s.headTilt, target.headTilt, SMOOTHING, delta)
    s.torsoTwist = damp(s.torsoTwist, target.torsoTwist, SMOOTHING, delta)
    // The mouth tracks loudness faster than the body, or speech looks dubbed.
    s.mouth = damp(s.mouth, Math.max(MOUTH_AT_REST, mouthOpenness(loudness())), SMOOTHING * 2.2, delta)
    s.pitch = damp(s.pitch, pose.headPitch, SMOOTHING * 0.55, delta)
    s.yaw = damp(s.yaw, pose.headYaw, SMOOTHING * 0.55, delta)
    s.lean = damp(s.lean, pose.lean, SMOOTHING * 0.55, delta)

    const breath = Math.sin(clock.current * 1.6) * 0.02 * pose.sway
    const drift = activity === 'thinking' ? Math.sin(clock.current * 0.9) * 0.05 : 0

    const head = vrm.humanoid.getNormalizedBoneNode('head')
    if (head) {
      head.rotation.x = s.headTilt + s.pitch + breath * 0.5 - lift * 0.12
      head.rotation.y = s.torsoTwist * 0.6 + s.yaw + drift
      head.rotation.z = s.yaw * 0.25
    }

    const neck = vrm.humanoid.getNormalizedBoneNode('neck')
    if (neck) neck.rotation.x = s.pitch * 0.35

    const chest =
      vrm.humanoid.getNormalizedBoneNode('upperChest') ??
      vrm.humanoid.getNormalizedBoneNode('chest') ??
      vrm.humanoid.getNormalizedBoneNode('spine')
    if (chest) {
      chest.rotation.y = s.torsoTwist * 0.4
      chest.rotation.x = breath * 0.6 - lift * 0.04 + s.lean * 0.25
    }

    const expressions = vrm.expressionManager
    if (expressions) {
      // One viseme only. Blending several stacks their morphs past full weight
      // at speech volumes, which distorts the face -- on this model it dragged
      // the eyes shut while talking.
      expressions.setValue('aa', s.mouth)

      // 'happy' and 'relaxed' are authored as closed-eye expressions on many
      // models, so they are held well below full weight; the others reshape
      // only the brow and mouth and can run stronger.
      const closesEyes = vrmEmotion === 'happy' || vrmEmotion === 'relaxed'
      const emotionWeight = closesEyes ? 0.3 : 0.6
      for (const preset of ['happy', 'angry', 'sad', 'relaxed', 'surprised'] as const) {
        expressions.setValue(preset, preset === vrmEmotion ? emotionWeight : 0)
      }

      if (clock.current > nextBlink.current) {
        blink.current = 1
        nextBlink.current =
          clock.current + (2.2 + Math.random() * 3.4) / Math.max(pose.blinkRate, 0.2)
      }
      blink.current = damp(blink.current, 0, 16, delta)
      // An expression that already narrows the eyes must not also blink, or
      // they close entirely.
      const narrowed = closesEyes ? emotionWeight : 0
      expressions.setValue('blink', Math.max(0, blink.current - narrowed))

      // Gaze morphs distort the eyes past low weights, so the head carries
      // most of the movement and the eyes only hint at it.
      expressions.setValue('lookLeft', Math.min(0.3, Math.max(0, s.yaw)))
      expressions.setValue('lookRight', Math.min(0.3, Math.max(0, -s.yaw)))
    }

    vrm.update(delta)
  })

  return vrm ? <primitive object={vrm.scene} /> : null
}
