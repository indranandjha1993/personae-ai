/** The avatar viewport: a close portrait framed on the character's face. */

import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'

import type { AudioFeatures } from '../audio/playback'
import type { MouthWeights } from '../audio/speech-timeline'
import { DEFAULT_AVATAR, type AvatarConfig } from './config'
import { recordMetric } from '../diagnostics'

import { Avatar } from './Avatar'
import { type Activity } from './expression-map'

function FrameMetrics() {
  const elapsed = useRef(0)
  useFrame((_, delta) => {
    elapsed.current += delta
    if (elapsed.current >= 1) {
      recordMetric('render_frame_ms', delta * 1000)
      elapsed.current = 0
    }
  })
  return null
}

export interface AvatarStageProps {
  quality?: 'auto' | 'high' | 'low'
  avatar?: AvatarConfig
  mouthCues?: () => MouthWeights | null
  gesture: string
  emotion: string
  activity: Activity
  features: () => AudioFeatures
}

interface Bounds {
  headY: number
  /** The very top of the model, hair included. */
  topY: number
  height: number
}

/**
 * Frames the upper body from the model's measured head position.
 *
 * Head to roughly the waist, the way a video call frames someone: her hands
 * have to be in shot for gesture to mean anything, while the face stays large
 * enough to read expression and lip sync.
 */
function FrameUpperBody({ bounds }: { bounds: Bounds | null }) {
  const camera = useThree((state) => state.camera)
  const aspect = useThree((state) => state.size.width / Math.max(1, state.size.height))

  useEffect(() => {
    if (!bounds) return
    // A little headroom above the crown, down to about the waist below. The
    // head bone is the skull base, so headroom must come from the measured
    // top of the model or the hair is cropped.
    const top = bounds.topY + bounds.height * 0.04
    const bottom = bounds.headY - bounds.height * 0.34
    const focusY = (top + bottom) / 2
    const span = top - bottom
    const fov = 'fov' in camera ? camera.fov : 30
    // Distance at which that span fills the frame vertically.
    const distance = span / 2 / Math.tan((fov * Math.PI) / 360) * Math.max(1, 0.85 / aspect)

    camera.position.set(0, focusY, distance)
    camera.lookAt(new THREE.Vector3(0, focusY, 0))
    camera.updateProjectionMatrix()
  }, [bounds, camera, aspect])

  return null
}

function AvatarViewport({
  quality = 'auto',
  avatar = DEFAULT_AVATAR,
  mouthCues,
  gesture,
  emotion,
  activity,
  features,
}: AvatarStageProps) {
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const [failure, setFailure] = useState('')
  const [attempt, setAttempt] = useState(0)

  const handleError = useCallback((message: string) => { setFailure(message) }, [])
  const handleFramed = useCallback((measured: Bounds) => { setBounds(measured) }, [])

  if (failure !== '') {
    return (
      <div className="stage stage--empty">
        <p className="stage-title">Avatar unavailable</p>
        <p className="stage-hint">
          {failure} Your conversation can continue without the avatar.
        </p>
        <button type="button" onClick={() => { setFailure(''); setBounds(null); setAttempt((n) => n + 1) }}>Retry avatar</button>
      </div>
    )
  }

  return (
    <div className="stage">
        {!bounds && <p role="status" style={{ position: 'absolute', zIndex: 1 }}>Loading avatar…</p>}
        <Canvas key={attempt} dpr={quality === 'low' ? 1 : [1, quality === 'high' ? 2 : 1.5]} onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', (event) => {
            event.preventDefault()
            setFailure('The graphics connection was lost.')
          }, { once: true })
        }} fallback={<p>3D graphics are unavailable in this browser.</p>} camera={{ position: [0, 1.15, 1.25], fov: 30 }} gl={{ alpha: true }}>
          <FrameUpperBody bounds={bounds} />
          <FrameMetrics />
          {/* Matches the three-vrm basic example: one normalised directional
              light at Math.PI, which is what MToon is authored against. */}
          <directionalLight position={[1, 1, 1]} intensity={Math.PI} />
          <ambientLight intensity={0.6} />
          {/* A rim light that moves with her head, which no amount of CSS
              glow can imitate. Kept low so MToon's toon shading survives. */}
          <directionalLight position={[-1.6, 1.4, -1.2]} intensity={0.7} color="#8b7fd4" />
          <Suspense fallback={null}>
            <Avatar
              modelUrl={avatar.model_url}
              avatarConfig={avatar}
              mouthCues={mouthCues}
              gesture={gesture}
              emotion={emotion}
              activity={activity}
              features={features}
              onError={handleError}
              onFramed={handleFramed}
            />
          </Suspense>
        </Canvas>
    </div>
  )
}

/** Remount loading state when an appearance changes, without resetting conversation. */
export function AvatarStage(props: AvatarStageProps) {
  return <AvatarViewport key={JSON.stringify(props.avatar ?? DEFAULT_AVATAR)} {...props} />
}
