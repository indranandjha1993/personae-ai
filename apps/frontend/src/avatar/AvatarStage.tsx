/**
 * The avatar viewport.
 *
 * A VRM model is a large binary asset with its own licence, so none is
 * committed. The stage therefore has to work with no model present: it explains
 * how to add one rather than rendering an empty canvas.
 */

import { Canvas } from '@react-three/fiber'
import { Suspense, useCallback, useState } from 'react'

import { Avatar } from './Avatar'

/** Served from public/, which is gitignored for models. */
const MODEL_URL = '/avatar.vrm'

export interface AvatarStageProps {
  gesture: string
  emotion: string
  loudness: () => number
}

export function AvatarStage({ gesture, emotion, loudness }: AvatarStageProps) {
  const [failure, setFailure] = useState('')
  const handleError = useCallback((message: string) => { setFailure(message) }, [])

  if (failure !== '') {
    return (
      <div className="stage stage--empty">
        <p className="stage-title">No avatar model loaded</p>
        <p className="stage-hint">
          Drop a <code>.vrm</code> file at <code>apps/frontend/public/avatar.vrm</code> and
          reload. Models are not committed: they are large and carry their own licence.
          Free avatars are available from <strong>VRoid Hub</strong>, or you can make one
          with <strong>VRoid Studio</strong>.
        </p>
        <p className="stage-cue">
          Gesture: {gesture} · Emotion: {emotion}
        </p>
      </div>
    )
  }

  return (
    <div className="stage">
      <Canvas camera={{ position: [0, 1.35, 1.9], fov: 30 }} shadows={false}>
        <ambientLight intensity={2.2} />
        <directionalLight position={[1.5, 2.5, 2]} intensity={1.4} />
        <Suspense fallback={null}>
          <Avatar
            modelUrl={MODEL_URL}
            gesture={gesture}
            emotion={emotion}
            loudness={loudness}
            onError={handleError}
          />
        </Suspense>
      </Canvas>
    </div>
  )
}
