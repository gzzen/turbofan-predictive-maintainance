import React from 'react'

interface Props {
  rul: number | null
  thresholdCycles: number
  cycle: number | null
  totalCycles: number | null
  maintenanceAdvisory: boolean
}

const RUL_CAP = 125 // matches transformer.py RUL_CAP

function rulColor(rul: number, threshold: number): string {
  if (rul <= threshold) return '#ef4444'       // red
  if (rul <= threshold * 2) return '#f59e0b'   // amber
  return '#10b981'                             // emerald
}

// Helpers for the SVG arc gauge
const toRad = (deg: number) => (deg * Math.PI) / 180
const arcPt = (cx: number, cy: number, r: number, deg: number) => ({
  x: cx + r * Math.cos(toRad(deg)),
  y: cy + r * Math.sin(toRad(deg)),
})

export const RULGauge = React.memo(function RULGauge({
  rul,
  thresholdCycles,
  cycle,
  totalCycles,
  maintenanceAdvisory,
}: Props) {
  const cx = 100
  const cy = 105
  const r = 78
  const startDeg = -215
  const endDeg = 35
  const span = endDeg - startDeg

  const fraction = rul !== null ? Math.min(Math.max(rul, 0), RUL_CAP) / RUL_CAP : 0
  const fillDeg = startDeg + fraction * span
  const largeArc = fraction * span > 180 ? 1 : 0

  const trackS = arcPt(cx, cy, r, startDeg)
  const trackE = arcPt(cx, cy, r, endDeg)
  const fillE = arcPt(cx, cy, r, fillDeg)

  const threshFraction = thresholdCycles / RUL_CAP
  const threshDeg = startDeg + threshFraction * span
  const threshOuter = arcPt(cx, cy, r, threshDeg)
  const threshInner = arcPt(cx, cy, r - 12, threshDeg)

  const color = rul !== null ? rulColor(rul, thresholdCycles) : '#6b7280'
  const cycleProgress = cycle !== null && totalCycles ? cycle / totalCycles : 0

  return (
    <div className="flex flex-col items-center w-full">
      <svg viewBox="0 0 200 170" className="w-56 h-44">
        {/* Background track */}
        <path
          d={`M ${trackS.x} ${trackS.y} A ${r} ${r} 0 1 1 ${trackE.x} ${trackE.y}`}
          fill="none"
          stroke="#1f2937"
          strokeWidth="14"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {rul !== null && fraction > 0 && (
          <path
            d={`M ${trackS.x} ${trackS.y} A ${r} ${r} 0 ${largeArc} 1 ${fillE.x} ${fillE.y}`}
            fill="none"
            stroke={color}
            strokeWidth="14"
            strokeLinecap="round"
          />
        )}
        {/* Maintenance threshold tick mark */}
        <line
          x1={threshInner.x} y1={threshInner.y}
          x2={threshOuter.x} y2={threshOuter.y}
          stroke="#f59e0b"
          strokeWidth="3"
        />
        {/* RUL value */}
        <text
          x={cx} y={cy - 4}
          textAnchor="middle"
          fill={color}
          fontSize="32"
          fontWeight="bold"
          fontFamily="ui-monospace, monospace"
        >
          {rul !== null ? Math.round(rul) : '—'}
        </text>
        <text x={cx} y={cy + 16} textAnchor="middle" fill="#6b7280" fontSize="11">
          cycles remaining
        </text>
        <text x={cx} y={cy + 30} textAnchor="middle" fill="#4b5563" fontSize="10">
          threshold {thresholdCycles}
        </text>
      </svg>

      {/* Cycle progress bar */}
      {totalCycles !== null && (
        <div className="w-56 mt-1">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Cycle {cycle ?? 0}</span>
            <span>{totalCycles}</span>
          </div>
          <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 rounded-full transition-all duration-300"
              style={{ width: `${cycleProgress * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Maintenance advisory banner */}
      {maintenanceAdvisory && (
        <div className="mt-4 w-full text-center px-4 py-2 rounded-lg bg-red-950/60 border border-red-700 text-red-400 text-xs font-semibold tracking-widest uppercase animate-pulse">
          Maintenance Required
        </div>
      )}
    </div>
  )
})
