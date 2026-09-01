/**
 * The avatar viewport and its model picker.
 *
 * Models are large licensed binaries and are not committed, so the viewport
 * always has a procedural figure to fall back on and only offers the models
 * actually present on disk.
 */

import { Canvas, useThree } from '@react-three/fiber'
import { Suspense, useCallback, useEffect, useState } from 'react'
import * as THREE from 'three'

import { Avatar } from './Avatar'
import { FallbackFigure } from './FallbackFigure'
import { type Activity } from './expression-map'
import { BUILT_IN, findAvailableModels, type ModelChoice } from './models'

export interface AvatarStageProps {
  accent: string
  gesture: string
  emotion: string
  activity: Activity
  loudness: () => number
}

interface Bounds {
  headY: number
  height: number
  floorY: number
}

/**
 * Points the camera at the upper body once the model's real size is known.
 *
 * Models vary in height and origin, so a fixed camera frames some of them at
 * the knees. Framing from measured bounds works for any model.
 */
function FrameCamera({ bounds }: { bounds: Bounds | null }) {
  const camera = useThree((state) => state.camera)

  useEffect(() => {
    if (!bounds) return
    // Aim just below the head: the face carries the expression, and a little
    // chest keeps the gestures visible.
    const focusY = bounds.headY - bounds.height * 0.16
    camera.position.set(0, focusY, bounds.height * 1.15)
    camera.lookAt(new THREE.Vector3(0, focusY, 0))
    camera.updateProjectionMatrix()
  }, [bounds, camera])

  return null
}

export function AvatarStage({
  accent,
  gesture,
  emotion,
  activity,
  loudness,
}: AvatarStageProps) {
  const [available, setAvailable] = useState<ModelChoice[]>([])
  const [selected, setSelected] = useState<ModelChoice>(BUILT_IN)
  const [bounds, setBounds] = useState<Bounds | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    findAvailableModels(controller.signal)
      .then((models) => {
        setAvailable(models)
        // Prefer a real model when one is installed; the built-in figure is a
        // fallback, not the intended experience.
        const first = models[0]
        if (first) setSelected(first)
      })
      .catch(() => { setAvailable([]) })
    return () => { controller.abort() }
  }, [])

  const handleError = useCallback(() => { setSelected(BUILT_IN) }, [])
  const handleFramed = useCallback((measured: Bounds) => { setBounds(measured) }, [])

  const choices = [...available, BUILT_IN]
  const usingModel = selected.url !== ''

  return (
    <div className="stage-wrap">
      <div className="stage">
        <Canvas camera={{ position: [0, 1.35, 1.9], fov: 32 }}>
          <FrameCamera bounds={usingModel ? bounds : null} />
          <ambientLight intensity={1.6} />
          <directionalLight position={[2, 3, 2]} intensity={1.8} />
          <directionalLight position={[-2, 1, -1]} intensity={0.5} color="#8fa3bf" />
          <Suspense fallback={null}>
            {usingModel ? (
              <Avatar
                key={selected.id}
                modelUrl={selected.url}
                gesture={gesture}
                emotion={emotion}
                activity={activity}
                loudness={loudness}
                onError={handleError}
                onFramed={handleFramed}
              />
            ) : (
              <FallbackFigure
                accent={accent}
                gesture={gesture}
                emotion={emotion}
                activity={activity}
                loudness={loudness}
              />
            )}
          </Suspense>
        </Canvas>
      </div>

      {choices.length > 1 && (
        <div className="models" role="group" aria-label="Avatar model">
          {choices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              className="model"
              aria-pressed={selected.id === choice.id}
              title={choice.credit}
              onClick={() => {
                setBounds(null)
                setSelected(choice)
              }}
            >
              {choice.name}
            </button>
          ))}
        </div>
      )}
      <p className="model-credit">{selected.credit}</p>
    </div>
  )
}
