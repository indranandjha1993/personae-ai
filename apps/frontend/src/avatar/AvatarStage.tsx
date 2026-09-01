/**
 * The avatar viewport.
 *
 * A VRM model is a large licensed binary, so none is committed. Rather than
 * showing an empty box until someone supplies one, a procedural figure is drawn
 * by default and the VRM takes over automatically when a model is present. Both
 * are driven by the same cues, so the conversation looks alive either way.
 */

import { Canvas } from '@react-three/fiber'
import { Suspense, useCallback, useEffect, useState } from 'react'

import { Avatar } from './Avatar'
import { FallbackFigure } from './FallbackFigure'

/** Served from public/, which is gitignored for models. */
const MODEL_URL = '/avatar.vrm'

export interface AvatarStageProps {
  accent: string
  gesture: string
  emotion: string
  loudness: () => number
}

type ModelState = 'checking' | 'present' | 'absent'

export function AvatarStage({ accent, gesture, emotion, loudness }: AvatarStageProps) {
  const [model, setModel] = useState<ModelState>('checking')

  useEffect(() => {
    const controller = new AbortController()
    // A HEAD request avoids downloading tens of megabytes just to find out
    // whether a model exists.
    fetch(MODEL_URL, { method: 'HEAD', signal: controller.signal })
      .then((response) => {
        const type = response.headers.get('content-type') ?? ''
        // A dev server happily returns index.html for a missing file, so a 200
        // alone is not proof that a model is there.
        setModel(response.ok && !type.includes('text/html') ? 'present' : 'absent')
      })
      .catch(() => { setModel('absent') })
    return () => { controller.abort() }
  }, [])

  const handleError = useCallback(() => { setModel('absent') }, [])

  return (
    <div className="stage">
      <Canvas camera={{ position: [0, 0.85, 2.6], fov: 32 }}>
        <ambientLight intensity={1.6} />
        <directionalLight position={[2, 3, 2]} intensity={1.8} />
        <directionalLight position={[-2, 1, -1]} intensity={0.5} color="#8fa3bf" />
        <Suspense fallback={null}>
          {model === 'present' ? (
            <Avatar
              modelUrl={MODEL_URL}
              gesture={gesture}
              emotion={emotion}
              loudness={loudness}
              onError={handleError}
            />
          ) : (
            <FallbackFigure
              accent={accent}
              gesture={gesture}
              emotion={emotion}
              loudness={loudness}
            />
          )}
        </Suspense>
      </Canvas>
      {model === 'absent' && (
        <p className="stage-note">
          Using the built-in figure. Drop a <code>.vrm</code> at{' '}
          <code>apps/frontend/public/avatar.vrm</code> for a full 3D character.
        </p>
      )}
    </div>
  )
}
