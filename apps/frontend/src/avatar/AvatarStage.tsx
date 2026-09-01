/**
 * The avatar viewport: a close portrait of the character's face.
 *
 * Framed on the head deliberately. Expression -- eyes, mouth, the tilt of a
 * head while thinking -- is what this conveys, and a portrait does not depend
 * on how well a model's body happens to be rigged.
 */

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

/**
 * Frames the face once the model's real proportions are known.
 *
 * Models differ in height and origin, so a fixed camera crops some of them at
 * the chin. Measuring the head bone works for any of them.
 */
function FrameFace({ bounds }: { bounds: Bounds | null }) {
  const camera = useThree((state) => state.camera)

  useEffect(() => {
    if (!bounds) return
    // Eyes sit above the head bone, and a portrait wants them a little above
    // centre. The distance frames head and shoulders rather than filling the
    // frame with a face.
    const focusY = bounds.headY + bounds.height * 0.05
    camera.position.set(0, focusY, bounds.height * 0.62)
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
          {/* MToon materials are unlit: they take their tone from ambient light
              and ignore directional lights, which is why a scene lit only by
              directionals renders them black. */}
          <ambientLight intensity={3.2} />
          <directionalLight position={[1, 2, 3]} intensity={0.9} />
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
