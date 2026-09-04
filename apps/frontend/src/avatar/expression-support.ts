/**
 * Which of the expressions the face is driven through this model actually has.
 *
 * three-vrm ignores a weight set on an expression the model lacks -- silently,
 * every frame -- so a channel that is missing must be noticed at load and
 * given a stand-in, rather than assumed to be working.
 */

/** The brow expressions the emphasis tracker drives, when a model has them. */
export const BROW_EXPRESSIONS = ['eye_brow_up_L', 'eye_brow_up_R'] as const

export interface BrowChannel {
  /**
   * 'custom' when the model authors its own brows; 'surprised' rides the
   * standard preset instead, which lifts the brows on most VRoid faces.
   */
  mode: 'custom' | 'surprised'
  missing: string[]
}

export function browChannel(has: (name: string) => boolean): BrowChannel {
  const missing = BROW_EXPRESSIONS.filter((name) => !has(name))
  return { mode: missing.length === 0 ? 'custom' : 'surprised', missing }
}

/**
 * How much of the 'surprised' preset one full brow raise is worth.
 *
 * Kept low: the preset also widens the eyes and parts the lips, and at full
 * weight an accent would read as a start rather than a stress.
 */
export const SURPRISED_PER_BROW = 0.35
