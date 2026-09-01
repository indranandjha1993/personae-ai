/**
 * The avatar models available to the picker.
 *
 * Models are not committed -- they are large and carry their own licences -- so
 * this lists what the project knows how to offer, and each entry is probed at
 * runtime. Anything missing from public/models is simply not shown.
 */

export interface ModelChoice {
  id: string
  name: string
  url: string
  /** Shown so it is clear where each model came from and under what terms. */
  credit: string
}

export const MODEL_CHOICES: readonly ModelChoice[] = [
  {
    id: 'seed-san',
    name: 'Seed-san',
    url: '/models/seed-san.vrm',
    credit: 'VirtualCast, Inc. — VRM Public License 1.0',
  },
  {
    id: 'robert',
    name: 'Robert',
    url: '/models/robert.vrm',
    credit: 'Polygonal Mind — CC0',
  },
  {
    id: 'rose',
    name: 'Rose',
    url: '/models/rose.vrm',
    credit: 'Polygonal Mind — CC0',
  },
  {
    id: 'rabbit',
    name: 'Rabbit',
    url: '/models/rabbit.vrm',
    credit: 'Polygonal Mind — CC0',
  },
]

/** The built-in procedural figure, always available. */
export const BUILT_IN: ModelChoice = {
  id: 'built-in',
  name: 'Built-in figure',
  url: '',
  credit: 'Drawn in code — no model file needed',
}

/**
 * Check which models are actually present.
 *
 * A dev server answers 200 with index.html for a file that is not there, so the
 * content type is checked as well as the status.
 */
export async function findAvailableModels(signal?: AbortSignal): Promise<ModelChoice[]> {
  const checks = MODEL_CHOICES.map(async (choice) => {
    try {
      const response = await fetch(choice.url, { method: 'HEAD', ...(signal ? { signal } : {}) })
      const type = response.headers.get('content-type') ?? ''
      return response.ok && !type.includes('text/html') ? choice : null
    } catch {
      return null
    }
  })
  const settled = await Promise.all(checks)
  return settled.filter((choice): choice is ModelChoice => choice !== null)
}
