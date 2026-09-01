/**
 * A procedurally built character, used when no VRM model is supplied.
 *
 * The point of this project is to watch something react to the conversation, so
 * the viewport must never be empty. This figure is built from primitives -- no
 * asset, no licence, no download -- and is driven by exactly the same cues as a
 * VRM model, so behaviour is identical whichever renderer is active.
 */

import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

import { mouthOpenness, toPose, toVrmEmotion } from './expression-map'

const SMOOTHING = 9

/** Emotion tints, chosen to read clearly against the dark stage. */
const EMOTION_TINT: Record<string, string> = {
  neutral: '#8fa3bf',
  happy: '#ffd479',
  angry: '#ff8a7a',
  sad: '#8fa6d8',
  relaxed: '#8fd8bf',
  surprised: '#e0a3ff',
}

export interface FallbackFigureProps {
  accent: string
  gesture: string
  emotion: string
  loudness: () => number
}

export function FallbackFigure({ accent, gesture, emotion, loudness }: FallbackFigureProps) {
  const head = useRef<THREE.Group>(null)
  const torso = useRef<THREE.Group>(null)
  const leftArm = useRef<THREE.Group>(null)
  const rightArm = useRef<THREE.Group>(null)
  const mouth = useRef<THREE.Mesh>(null)
  const leftEye = useRef<THREE.Mesh>(null)
  const rightEye = useRef<THREE.Mesh>(null)

  const state = useRef({ armSwing: 0, headTilt: 0, torsoTwist: 0, mouth: 0, blink: 0 })
  const clock = useRef(0)
  const nextBlink = useRef(2)

  const accentColor = useMemo(() => new THREE.Color(accent), [accent])
  const tint = useMemo(() => new THREE.Color(EMOTION_TINT[toVrmEmotion(emotion)] ?? '#8fa3bf'), [emotion])

  useFrame((_, delta) => {
    clock.current += delta
    const now = clock.current
    const s = state.current
    const target = toPose(gesture)
    const damp = THREE.MathUtils.damp

    s.armSwing = damp(s.armSwing, target.armSwing, SMOOTHING, delta)
    s.headTilt = damp(s.headTilt, target.headTilt, SMOOTHING, delta)
    s.torsoTwist = damp(s.torsoTwist, target.torsoTwist, SMOOTHING, delta)
    // The mouth tracks loudness faster than the body moves, or speech looks dubbed.
    s.mouth = damp(s.mouth, mouthOpenness(loudness()), SMOOTHING * 2.2, delta)

    // Idle motion: without it a still figure reads as broken rather than waiting.
    const breath = Math.sin(now * 1.5) * 0.03
    const sway = Math.sin(now * 0.7) * 0.04

    if (torso.current) {
      torso.current.rotation.y = s.torsoTwist + sway
      torso.current.position.y = breath * 0.5
    }
    if (head.current) {
      head.current.rotation.x = s.headTilt + breath
      head.current.rotation.y = s.torsoTwist * 0.7 + sway * 0.5
    }
    if (leftArm.current) leftArm.current.rotation.z = 0.25 + s.armSwing
    if (rightArm.current) rightArm.current.rotation.z = -0.25 - s.armSwing

    if (mouth.current) {
      // Scale rather than translate, so the mouth opens from its centre.
      mouth.current.scale.set(1 + s.mouth * 0.35, 0.12 + s.mouth * 1.5, 1)
    }

    // Occasional blink, so the face does not stare.
    if (now > nextBlink.current) {
      s.blink = 1
      nextBlink.current = now + 2.5 + Math.random() * 3
    }
    s.blink = damp(s.blink, 0, 14, delta)
    const eyeScale = 1 - s.blink * 0.9
    leftEye.current?.scale.set(1, eyeScale, 1)
    rightEye.current?.scale.set(1, eyeScale, 1)
  })

  return (
    <group position={[0, -0.7, 0]}>
      <group ref={torso}>
        <mesh position={[0, 0.75, 0]}>
          <capsuleGeometry args={[0.28, 0.55, 8, 24]} />
          <meshStandardMaterial color={accentColor} roughness={0.55} metalness={0.15} />
        </mesh>

        <group ref={leftArm} position={[-0.32, 1.0, 0]}>
          <mesh position={[-0.1, -0.28, 0]}>
            <capsuleGeometry args={[0.075, 0.45, 6, 16]} />
            <meshStandardMaterial color={accentColor} roughness={0.6} />
          </mesh>
        </group>
        <group ref={rightArm} position={[0.32, 1.0, 0]}>
          <mesh position={[0.1, -0.28, 0]}>
            <capsuleGeometry args={[0.075, 0.45, 6, 16]} />
            <meshStandardMaterial color={accentColor} roughness={0.6} />
          </mesh>
        </group>

        <group ref={head} position={[0, 1.35, 0]}>
          <mesh>
            <sphereGeometry args={[0.27, 32, 32]} />
            <meshStandardMaterial color={tint} roughness={0.4} />
          </mesh>
          <mesh ref={leftEye} position={[-0.09, 0.05, 0.245]}>
            <sphereGeometry args={[0.035, 16, 16]} />
            <meshStandardMaterial color="#12151c" />
          </mesh>
          <mesh ref={rightEye} position={[0.09, 0.05, 0.245]}>
            <sphereGeometry args={[0.035, 16, 16]} />
            <meshStandardMaterial color="#12151c" />
          </mesh>
          <mesh ref={mouth} position={[0, -0.09, 0.245]}>
            <capsuleGeometry args={[0.055, 0.02, 4, 12]} />
            <meshStandardMaterial color="#12151c" />
          </mesh>
        </group>
      </group>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.12, 0]}>
        <circleGeometry args={[0.75, 48]} />
        <meshStandardMaterial color="#0d1016" roughness={1} />
      </mesh>
    </group>
  )
}
