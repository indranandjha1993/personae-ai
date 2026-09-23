/** Bounded, local measurements. No transcripts, credentials or remote telemetry. */
const samples = new Map<string, number[]>()
export function recordMetric(name: string, milliseconds: number): void {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return
  const values = samples.get(name) ?? []
  values.push(milliseconds)
  if (values.length > 200) values.shift()
  samples.set(name, values)
  window.dispatchEvent(new CustomEvent('personae:metric', { detail: { name, milliseconds } }))
}
export function metricSummary(): Record<string, { count: number; p50: number; p95: number }> {
  return Object.fromEntries([...samples].map(([name, values]) => {
    const sorted = [...values].sort((a, b) => a - b)
    return [name, { count: sorted.length,
      p50: sorted[Math.max(0, Math.ceil(sorted.length * 0.5) - 1)] ?? 0,
      p95: sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0 }]
  }))
}
export function downloadMetrics(): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(metricSummary(), null, 2)],
    { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'personae-metrics.json'
  anchor.click()
  setTimeout(() => { URL.revokeObjectURL(url) }, 0)
}
