/** The avatar viewport: a close portrait framed on the character's face. */

import { Canvas, useThree } from '@react-three/fiber'
import { Suspense, useCallback, useEffect, useState } from 'react'
import * as THREE from 'three'

import { Avatar } from './Avatar'
import { type Activity } from './expression-map'

const MODEL_URL = '/models/seed-san.vrm'
const MODEL_CREDIT = 'Seed-san by VirtualCast, Inc. — VRM Public License 1.0'

export interface AvatarStageProps {
  gesture: string
  emotion: string
  activity: Activity
  loudness: () => number
}

interface Bounds {
  headY: number
  height: number
}

/** Frames the face from the model's measured head position. */
function FrameFace({ bounds }: { bounds: Bounds | null }) {
  const camera = useThree((state) => state.camera)

  useEffect(() => {
    if (!bounds) return
    // Eyes sit above the head bone; a portrait wants them above centre.
    const focusY = bounds.headY + bounds.height * 0.035
    camera.position.set(0, focusY, bounds.height * 0.46)
    camera.lookAt(new THREE.Vector3(0, focusY, 0))
    camera.updateProjectionMatrix()
  }, [bounds, camera])

  return null
}

export function AvatarStage({ gesture, emotion, activity, loudness }: AvatarStageProps) {
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
    <div className="stage-wrap">
      <div className="stage">
        <Canvas camera={{ position: [0, 1.4, 0.55], fov: 26 }} gl={{ alpha: true }}>
          <FrameFace bounds={bounds} />
          {/* Matches the three-vrm basic example: one normalised directional
              light at Math.PI, which is what MToon is authored against. */}
          <directionalLight position={[1, 1, 1]} intensity={Math.PI} />
          <ambientLight intensity={0.6} />
          <Suspense fallback={null}>
            <Avatar
              modelUrl={MODEL_URL}
              gesture={gesture}
              emotion={emotion}
              activity={activity}
              loudness={loudness}
              onError={handleError}
              onFramed={handleFramed}
            />
          </Suspense>
        </Canvas>
      </div>
      <p className="model-credit">{MODEL_CREDIT}</p>
    </div>
  )
}
