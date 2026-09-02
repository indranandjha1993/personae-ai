/** The avatar viewport: a close portrait framed on the character's face. */

import { Canvas, useThree } from '@react-three/fiber'
import { Suspense, useCallback, useEffect, useState } from 'react'
import * as THREE from 'three'

import type { AudioFeatures } from '../audio/playback'
import { Avatar } from './Avatar'
import { type Activity } from './expression-map'

const MODEL_URL = '/models/seed-san.vrm'

export interface AvatarStageProps {
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
    const distance = span / 2 / Math.tan((fov * Math.PI) / 360)

    camera.position.set(0, focusY, distance)
    camera.lookAt(new THREE.Vector3(0, focusY, 0))
    camera.updateProjectionMatrix()
  }, [bounds, camera])

  return null
}

export function AvatarStage({
  gesture,
  emotion,
  activity,
  features,
}: AvatarStageProps) {
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const [failure, setFailure] = useState('')

  const handleError = useCallback((message: string) => { setFailure(message) }, [])
  const handleFramed = useCallback((measured: Bounds) => { setBounds(measured) }, [])

  if (failure !== '') {
    return (
      <div className="stage stage--empty">
        <p className="stage-title">Avatar unavailable</p>
        <p className="stage-hint">
          Place a <code>.vrm</code> model at <code>apps/frontend/public/models/seed-san.vrm</code>.
          Models are not committed: they are large and carry their own licence.
        </p>
      </div>
    )
  }

  return (
    <div className="stage">
        <Canvas camera={{ position: [0, 1.15, 1.25], fov: 30 }} gl={{ alpha: true }}>
          <FrameUpperBody bounds={bounds} />
          {/* Matches the three-vrm basic example: one normalised directional
              light at Math.PI, which is what MToon is authored against. */}
          <directionalLight position={[1, 1, 1]} intensity={Math.PI} />
          <ambientLight intensity={0.6} />
          {/* A rim light that moves with her head, which no amount of CSS
              glow can imitate. Kept low so MToon's toon shading survives. */}
          <directionalLight position={[-1.6, 1.4, -1.2]} intensity={0.7} color="#8b7fd4" />
          <Suspense fallback={null}>
            <Avatar
              modelUrl={MODEL_URL}
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
