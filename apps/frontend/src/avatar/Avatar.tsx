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

import type { AudioFeatures } from '../audio/playback'
import { BlinkController } from './blink'
import { EmphasisTracker } from './emphasis'
import { LipSync } from './lip-sync'
import { GazeController } from './gaze'
import { GesturePhaser } from './gesture-timing'
import { ATTEND, blendPoses, REST, toBodyPose } from './gestures'
import { ARM_BONES, loadMotions } from './motions'
import { applyBeat, applyBodyPose, applyMotion } from './rig'
import {
  ACTIVITY_POSE,
  toVrmEmotion,
  type Activity,
} from './expression-map'
import { browChannel, SURPRISED_PER_BROW, type BrowChannel } from './expression-support'

const SMOOTHING = 9

/** How long an authored clip takes to hand the arms back to the rig. */
const CLIP_FADE_SECONDS = 0.3

/** An authored clip in play, and where it is in handing the arms back. */
interface ActiveClip {
  action: THREE.AnimationAction
  duration: number
  /** Seconds into the fade-out; null while the clip still owns the arms. */
  fading: number | null
}

/**
 * Skin tint, multiplied over the model's own texture.
 *
 * A factor rather than a flat colour, so the painted shading and the blush at
 * the cheeks survive: white leaves the model exactly as its author made it,
 * and warmer or deeper tones shift it without flattening the detail.
 */
const SKIN_TINT = new THREE.Color(0.93, 0.78, 0.7)

/** Materials that make up her skin, by the names this model uses. */
const SKIN_MATERIALS = /^(body_bake|body_nm)$/

function tintSkin(object: THREE.Object3D): void {
  if (!(object instanceof THREE.Mesh)) return
  const material = object.material as THREE.Material | THREE.Material[]
  for (const entry of Array.isArray(material) ? material : [material]) {
    if (!SKIN_MATERIALS.test(entry.name)) continue
    // MToon keeps a separate shade colour for the lit and unlit sides; both
    // are tinted, or the shadowed half of her face stays the original tone.
    const tintable = entry as THREE.Material & {
      color?: THREE.Color
      shadeColorFactor?: THREE.Color
    }
    tintable.color?.multiply(SKIN_TINT)
    tintable.shadeColorFactor?.multiply(SKIN_TINT)
  }
}

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
  features: () => AudioFeatures
  onError: (message: string) => void
  onFramed: (bounds: { headY: number; topY: number; height: number }) => void
}

export function Avatar({
  modelUrl,
  gesture,
  emotion,
  activity,
  features,
  onError,
  onFramed,
}: AvatarProps) {
  const [vrm, setVrm] = useState<VRM | null>(null)
  const state = useRef({
    headTilt: 0,
    torsoTwist: 0,
    mouth: 0,
    pitch: 0,
    yaw: 0,
    lean: 0,
  })
  const clock = useRef(0)
  const posed = useRef(REST)
  const motionClock = useRef(0)
  const lastGesture = useRef('idle')
  const gaze = useRef(new GazeController())
  const blink = useRef(new BlinkController())
  const focus = useRef(new THREE.Vector3())
  const lip = useRef(new LipSync())
  const emphasis = useRef(new EmphasisTracker())
  const phaser = useRef(new GesturePhaser())
  const brows = useRef<BrowChannel>({ mode: 'custom', missing: [] })
  const mixer = useRef<THREE.AnimationMixer | null>(null)
  const clips = useRef(new Map<string, THREE.AnimationClip>())
  const active = useRef<ActiveClip | null>(null)
  const armBones = useRef<THREE.Object3D[]>([])
  // Where a clip put each arm bone this frame, so the rig's pose can be
  // blended toward it rather than overwriting it.
  const clipPose = useRef(new Map<THREE.Object3D, THREE.Quaternion>())

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
          // The prop arm is a separate mesh and simply goes.
          if (/robo/i.test(object.name)) object.visible = false

          tintSkin(object)
        })

        // The arms are posed every frame by the rig, which corrects for this
        // model binding with them raised rather than in a T-pose.

        loaded.scene.updateMatrixWorld(true)
        const headNode = loaded.humanoid.getNormalizedBoneNode('head')
        const box = new THREE.Box3().setFromObject(loaded.scene)
        const headY = headNode
          ? new THREE.Vector3().setFromMatrixPosition(headNode.matrixWorld).y
          : box.max.y * 0.93
        // The head bone sits at the base of the skull; the crown, hair
        // included, is the box top -- framing from the bone crops the head.
        onFramed({ headY, topY: box.max.y, height: box.max.y - box.min.y })

        // A weight set on an expression the model lacks is ignored without
        // a word; find out now which channels are real.
        const manager = loaded.expressionManager
        brows.current = browChannel((name) => manager?.getExpression(name) != null)
        if (brows.current.missing.length > 0) {
          console.warn(
            `avatar: model has no ${brows.current.missing.join(', ')}; ` +
              'brow accents will ride the surprised preset instead',
          )
        }

        armBones.current = ARM_BONES.flatMap((bone) => {
          const node = loaded.humanoid.getNormalizedBoneNode(bone)
          return node ? [node] : []
        })
        mixer.current = new THREE.AnimationMixer(loaded.scene)
        void loadMotions(loaded).then((found) => {
          if (!cancelled) clips.current = found
        })

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

  /** Start the authored clip for a gesture, or begin handing the arms back. */
  const playClip = (name: string): void => {
    const player = mixer.current
    const clip = clips.current.get(name)
    if (!player || !clip) {
      if (active.current && active.current.fading === null) active.current.fading = 0
      return
    }
    if (active.current) active.current.action.stop()
    const action = player.clipAction(clip)
    action.reset()
    action.setLoop(THREE.LoopOnce, 1)
    // Held on its last frame while the rig eases back in underneath it.
    action.clampWhenFinished = true
    action.play()
    active.current = { action, duration: clip.duration, fading: null }
  }

  /** How much of the arms a clip owns this frame, 0 to 1, advancing its fade. */
  const clipWeight = (delta: number): number => {
    const current = active.current
    if (!current) return 0
    if (current.fading === null) {
      if (current.action.time < current.duration - 1e-3) return 1
      current.fading = 0
    }
    current.fading += delta
    const weight = 1 - Math.min(1, current.fading / CLIP_FADE_SECONDS)
    if (weight <= 0) {
      current.action.stop()
      active.current = null
    }
    return weight
  }

  // useFrame runs on the render loop, outside React's render phase, so mutating
  // the scene graph here is the intended pattern rather than a violation.
  /* eslint-disable react-hooks/immutability */
  useFrame(({ camera }, delta) => {
    if (!vrm) return
    clock.current += delta

    const s = state.current
    const damp = THREE.MathUtils.damp
    const vrmEmotion = toVrmEmotion(emotion)
    const pose = ACTIVITY_POSE[activity]
    const lift = EMOTION_POSTURE[vrmEmotion] ?? 0
    const speaking = activity === 'speaking'

    // One analyser read per frame, shared by the mouth, the accent tracker
    // and the gesture's timing.
    const voice = features()
    const mouth = lip.current.update(voice, delta)
    const accent = emphasis.current.update(voice.rms, delta, speaking)
    blink.current.onPause(lip.current.pauseSeconds)

    // A gesture is cued per sentence. Its stroke waits for the voice to
    // stress a word, and a motion or clip plays from the moment it lands, so
    // the clocks restart on every change rather than running from page load.
    const wanted = toBodyPose(gesture)
    if (gesture !== lastGesture.current) {
      lastGesture.current = gesture
      motionClock.current = 0
      if (gesture === 'idle') phaser.current.release()
      else phaser.current.begin()
      playClip(gesture)
    }
    motionClock.current += delta
    const timing = phaser.current.update(delta, accent.accent)

    // Between gestures the hands wait up, not down, for as long as she is
    // talking; only silence brings them to rest.
    const base = speaking ? ATTEND : REST
    const target = gesture === 'idle' ? base : blendPoses(base, wanted, timing.amount)
    posed.current = blendPoses(posed.current, target, Math.min(1, delta * timing.ease))

    // An authored clip, where one exists, moves the arms; the rig's pose is
    // blended toward it by the clip's weight so the handover is a crossfade
    // rather than a cut. The mixer runs first so its result can be read.
    const player = mixer.current
    const owned = player ? clipWeight(delta) : 0
    if (player && owned > 0) {
      player.update(delta)
      for (const bone of armBones.current) {
        const saved = clipPose.current.get(bone) ?? new THREE.Quaternion()
        saved.copy(bone.quaternion)
        clipPose.current.set(bone, saved)
      }
    }
    applyBodyPose(vrm, posed.current)
    if (owned > 0) {
      for (const bone of armBones.current) {
        const saved = clipPose.current.get(bone)
        if (saved) bone.quaternion.slerp(saved, owned)
      }
    } else {
      applyBeat(vrm, timing.beat)
    }

    const headTarget = { headTilt: posed.current.headTilt, torsoTwist: posed.current.torsoTwist }

    s.headTilt = damp(s.headTilt, headTarget.headTilt, SMOOTHING, delta)
    s.torsoTwist = damp(s.torsoTwist, headTarget.torsoTwist, SMOOTHING, delta)
    // The mouth tracks loudness faster than the body, or speech looks dubbed.
    s.pitch = damp(s.pitch, pose.headPitch, SMOOTHING * 0.55, delta)
    s.yaw = damp(s.yaw, pose.headYaw, SMOOTHING * 0.55, delta)
    s.lean = damp(s.lean, pose.lean, SMOOTHING * 0.55, delta)

    const breath = Math.sin(clock.current * 1.6) * 0.02 * pose.sway
    const drift = activity === 'thinking' ? Math.sin(clock.current * 0.9) * 0.05 : 0

    const head = vrm.humanoid.getNormalizedBoneNode('head')
    if (head) {
      // The nod is additive, so it rides on top of the pose rather than
      // fighting the damped values.
      head.rotation.x = s.headTilt + s.pitch + breath * 0.5 - lift * 0.12 + accent.nod
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

    // After the absolute head and arm writes, so the oscillation rides on top
    // of the pose instead of being overwritten by it.
    if (wanted.motion) applyMotion(vrm, wanted.motion, motionClock.current)

    const blinkCtl = blink.current
    const expressions = vrm.expressionManager
    if (expressions) {
      // The full mouth: five vowel shapes blended across an openness and
      // frontness plane, with the jaw and width driven separately so the mouth
      // can be quick without the vowel identity flickering.
      // The jaw rides under the vowels as a floor: with every vowel at zero
      // the lips still part slightly, so the mouth line never disappears.
      expressions.setValue('aa', Math.min(1, mouth.aa + mouth.jaw))
      expressions.setValue('ih', mouth.ih)
      expressions.setValue('ou', mouth.ou)
      expressions.setValue('ee', mouth.ee)
      expressions.setValue('oh', mouth.oh)

      // 'happy' and 'relaxed' are authored as closed-eye expressions on many
      // models, so they are held well below full weight; the others reshape
      // only the brow and mouth and can run stronger.
      const closesEyes = vrmEmotion === 'happy' || vrmEmotion === 'relaxed'
      const emotionWeight = closesEyes ? 0.3 : 0.6
      // On a model without brow expressions, an accent lifts the brows
      // through 'surprised' instead -- the one preset that raises them.
      const browLift =
        brows.current.mode === 'surprised'
          ? Math.max(accent.browLeft, accent.browRight) * SURPRISED_PER_BROW
          : 0
      for (const preset of ['happy', 'angry', 'sad', 'relaxed', 'surprised'] as const) {
        const weight = preset === vrmEmotion ? emotionWeight : 0
        expressions.setValue(preset, preset === 'surprised' ? Math.max(weight, browLift) : weight)
      }

      // An expression that already narrows the eyes shortens the blink rather
      // than stacking with it.
      blinkCtl.onActivity(activity)
      const lid = blinkCtl.update(delta, activity, closesEyes ? emotionWeight : 0)
      expressions.setValue('blink', lid)

      // Brows move unevenly on stressed words; a face that raises both by the
      // same amount reads as a mask.
      if (brows.current.mode === 'custom') {
        expressions.setValue('eye_brow_up_L', accent.browLeft)
        expressions.setValue('eye_brow_up_R', accent.browRight)
      }
    }

    // Gaze last, before the update that applies it. Pointing lookAt at the
    // camera makes the eyes hold the viewer through head movement -- the eyes
    // counter-rotate for free, where the old code pushed them the same way the
    // head turned.
    const lookAt = vrm.lookAt
    if (lookAt) {
      lookAt.lookAt(camera.getWorldPosition(focus.current))
      const aim = gaze.current.update(activity, delta, 0, false)
      blinkCtl.onSaccade(gaze.current.lastSaccadeDegrees)
      lookAt.yaw += aim.yaw
      lookAt.pitch += aim.pitch
    }

    vrm.update(delta)
  })
  /* eslint-enable react-hooks/immutability */

  return vrm ? <primitive object={vrm.scene} /> : null
}
