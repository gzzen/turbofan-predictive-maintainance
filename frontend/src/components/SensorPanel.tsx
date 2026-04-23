import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FixedSizeList } from 'react-window'
import type { RULEvent } from '../api/schema'
import { SensorRow, type SensorReading } from './SensorRow'

const SENSOR_NAMES = Array.from({ length: 21 }, (_, i) => `s_${i + 1}`)
const ROW_HEIGHT = 40

interface Props {
  latest: RULEvent | null
  /** Callback with sensor panel render duration in ms (for perf tracking) */
  onRenderTime?: (durationMs: number) => void
}

// Per-sensor running min/max for bar normalisation across the stream lifetime
type SensorRange = Record<string, { min: number; max: number }>

export function SensorPanel({ latest, onRenderTime }: Props) {
  const rangeRef = useRef<SensorRange>({})
  const renderStartRef = useRef<number>(0)

  const [sensors, setSensors] = useState<SensorReading[]>(() =>
    SENSOR_NAMES.map((name) => ({ name, value: 0, min: 0, max: 1 })),
  )

  // Mark render start when a new event arrives
  useEffect(() => {
    if (!latest) return
    renderStartRef.current = performance.now()

    setSensors(
      SENSOR_NAMES.map((name) => {
        const value = latest.sensors[name] ?? 0
        const prev = rangeRef.current[name] ?? { min: value, max: value }
        const range = { min: Math.min(prev.min, value), max: Math.max(prev.max, value) }
        rangeRef.current[name] = range
        return { name, value, min: range.min, max: range.max }
      }),
    )
  }, [latest])

  // Measure time from render start to commit (approximates reconciliation cost)
  useEffect(() => {
    if (renderStartRef.current === 0) return
    const durationMs = performance.now() - renderStartRef.current
    renderStartRef.current = 0
    onRenderTime?.(durationMs)
  })

  // Stable references for react-window
  const itemData = useMemo(() => ({ sensors }), [sensors])
  const itemKey = useCallback((index: number) => SENSOR_NAMES[index], [])

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 overflow-hidden h-full">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-200">Sensor Readings</h2>
        <span className="text-xs text-gray-500 font-mono">
          {SENSOR_NAMES.length} sensors · react-window
        </span>
      </div>

      {/* FixedSizeList renders only the visible rows in the DOM.
          With 21 sensors and ROW_HEIGHT=40 the full list fits without scrolling,
          but the virtualisation still prevents unnecessary re-renders via
          the memoised SensorRow comparator. */}
      <FixedSizeList
        height={SENSOR_NAMES.length * ROW_HEIGHT}
        itemCount={SENSOR_NAMES.length}
        itemSize={ROW_HEIGHT}
        width="100%"
        itemData={itemData}
        itemKey={itemKey}
      >
        {SensorRow}
      </FixedSizeList>
    </div>
  )
}
