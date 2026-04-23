import React from 'react'
import type { ListChildComponentProps } from 'react-window'

export interface SensorReading {
  name: string    // 's_1' … 's_21'
  value: number
  min: number
  max: number
}

export interface SensorRowData {
  sensors: SensorReading[]
}

function barColor(norm: number): string {
  if (norm > 0.85) return 'bg-red-500'
  if (norm > 0.65) return 'bg-amber-500'
  return 'bg-emerald-500'
}

// React.memo with a custom comparator: only re-render when this row's value
// actually changes. react-window will re-invoke the render for any row whose
// index is visible on scroll, so the comparator prevents spurious work when
// only the scroll position changes.
export const SensorRow = React.memo(
  function SensorRow({ index, style, data }: ListChildComponentProps<SensorRowData>) {
    const sensor = data.sensors[index]
    if (!sensor) return null

    const norm =
      sensor.max > sensor.min
        ? Math.min(1, Math.max(0, (sensor.value - sensor.min) / (sensor.max - sensor.min)))
        : 0.5

    return (
      <div
        style={style}
        className="flex items-center gap-3 px-3 border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
      >
        {/* Sensor name */}
        <span className="w-9 text-xs font-mono text-gray-500 shrink-0">{sensor.name}</span>

        {/* Normalised bar */}
        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-150 ${barColor(norm)}`}
            style={{ width: `${norm * 100}%` }}
          />
        </div>

        {/* Raw value */}
        <span className="w-20 text-right text-xs font-mono text-gray-300 shrink-0 tabular-nums">
          {sensor.value.toFixed(3)}
        </span>
      </div>
    )
  },
  // Custom equality: only re-render if this row's sensor value changed
  (prev, next) =>
    prev.index === next.index &&
    prev.data.sensors[prev.index]?.value === next.data.sensors[next.index]?.value,
)
