import { useCallback, useEffect, useRef, useState } from 'react'

export interface PerfMetrics {
  /** Frames delivered per second, averaged over the last second */
  fps: number
  /** Average sensor panel render duration per stream tick (ms) */
  avgRenderMs: number
  /** Cumulative sensor panel re-renders since stream started */
  renderCount: number
  /** ms from stream start to first render with live data (null until first tick) */
  ttiMs: number | null
  /** Frames that exceeded 1.5× the 60 fps budget (>25 ms) */
  frameDrops: number
}

const FRAME_BUDGET_MS = 1_000 / 60 // 16.67 ms

export function usePerfMonitor(active: boolean) {
  const [metrics, setMetrics] = useState<PerfMetrics>({
    fps: 0,
    avgRenderMs: 0,
    renderCount: 0,
    ttiMs: null,
    frameDrops: 0,
  })

  const rafRef = useRef<number | null>(null)
  const renderTimesRef = useRef<number[]>([])
  const frameDropsRef = useRef(0)
  const startTimeRef = useRef<number>(0)
  const ttiRef = useRef<number | null>(null)
  const renderCountRef = useRef(0)

  // Called by SensorPanel after each render that consumed a new SSE tick
  const trackRender = useCallback((durationMs: number) => {
    renderCountRef.current++
    renderTimesRef.current.push(durationMs)
    if (renderTimesRef.current.length > 120) renderTimesRef.current.shift()

    if (ttiRef.current === null) {
      ttiRef.current = Math.round(performance.now() - startTimeRef.current)
    }
  }, [])

  useEffect(() => {
    if (!active) {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      return
    }

    startTimeRef.current = performance.now()
    let lastTs = performance.now()
    let frameCount = 0
    let accMs = 0

    const loop = (ts: number) => {
      const delta = ts - lastTs
      lastTs = ts
      frameCount++
      accMs += delta

      // A frame taking >1.5× the 60 fps budget is considered dropped
      if (delta > FRAME_BUDGET_MS * 1.5) {
        frameDropsRef.current++
      }

      if (accMs >= 1_000) {
        const fps = Math.round((frameCount / accMs) * 1_000)
        const renderTimes = renderTimesRef.current
        const avgRenderMs =
          renderTimes.length > 0
            ? Math.round((renderTimes.reduce((a, b) => a + b, 0) / renderTimes.length) * 100) / 100
            : 0

        setMetrics({
          fps,
          avgRenderMs,
          renderCount: renderCountRef.current,
          ttiMs: ttiRef.current,
          frameDrops: frameDropsRef.current,
        })

        frameCount = 0
        accMs = 0
      }

      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [active])

  return { metrics, trackRender }
}
