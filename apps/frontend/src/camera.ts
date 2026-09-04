/**
 * Camera stills for the model to look at.
 *
 * One downscaled JPEG per turn, not a video stream: a still is enough to answer
 * "what am I holding?", and a frame per second would cost tokens continuously.
 */

/**
 * Long edge of the captured still.
 *
 * Vision tokens scale with pixels, and every one of them is prefill before
 * she can start answering. 512 is plenty to tell what someone is holding up.
 */
const MAX_EDGE = 512
const JPEG_QUALITY = 0.7

export interface Camera {
  stream: MediaStream
  /** A downscaled JPEG of the current view, or null if it cannot be read yet. */
  grab: () => Promise<Blob | null>
  stop: () => void
}

export async function startCamera(): Promise<Camera> {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
  })

  const video = document.createElement('video')
  video.srcObject = stream
  video.muted = true
  video.playsInline = true
  // Detached from the DOM but not hidden: a display:none element is not
  // guaranteed to decode frames, which yields a black capture.
  video.style.position = 'fixed'
  video.style.opacity = '0'
  video.style.pointerEvents = 'none'
  video.style.width = '1px'
  video.style.height = '1px'
  document.body.appendChild(video)

  await video.play()
  // play() resolves before the first frame is decoded, so drawing immediately
  // copies an empty buffer. Wait for real pixels.
  await firstFrame(video)

  const canvas = document.createElement('canvas')

  return {
    stream,
    grab: async () => {
      const { videoWidth: width, videoHeight: height } = video
      if (width === 0 || height === 0) return null

      const scale = Math.min(1, MAX_EDGE / Math.max(width, height))
      canvas.width = Math.round(width * scale)
      canvas.height = Math.round(height * scale)

      const context = canvas.getContext('2d')
      if (!context) return null
      context.drawImage(video, 0, 0, canvas.width, canvas.height)

      return new Promise((resolve) => {
        canvas.toBlob((blob) => { resolve(blob) }, 'image/jpeg', JPEG_QUALITY)
      })
    },
    stop: () => {
      video.pause()
      video.srcObject = null
      video.remove()
      stream.getTracks().forEach((track) => { track.stop() })
    },
  }
}

/**
 * Resolve once the video has decoded a frame.
 *
 * requestVideoFrameCallback is exact where it exists; elsewhere waiting for
 * dimensions plus a tick is close enough for a still.
 */
async function firstFrame(video: HTMLVideoElement): Promise<void> {
  type FrameCallback = (callback: () => void) => number
  const request = (video as { requestVideoFrameCallback?: FrameCallback })
    .requestVideoFrameCallback

  if (request) {
    await new Promise<void>((resolve) => { request.call(video, resolve) })
    return
  }

  // Fallback: wait for dimensions, which appear with the first decoded frame.
  for (let attempt = 0; attempt < 20 && video.videoWidth === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
}

/** Scale a frame to fit within the long edge, preserving aspect ratio. */
export function fittedSize(
  width: number,
  height: number,
  maxEdge = MAX_EDGE,
): { width: number; height: number } {
  const scale = Math.min(1, maxEdge / Math.max(width, height))
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}
