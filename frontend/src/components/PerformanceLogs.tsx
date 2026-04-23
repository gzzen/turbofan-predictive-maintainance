import React, { useEffect, useRef, useState } from 'react'
import type { SSEState } from '../hooks/useSSE'
import type { PerfMetrics } from '../hooks/usePerf'

interface LogEntry {
  ts: number
  latencyMs: number
  payloadBytes: number
  fps: number
  avgRenderMs: number
  frameDrops: number
}

interface StatCardProps {
  label: string
  value: string
  accent?: boolean
}

function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <div className="bg-gray-900 px-3 py-2">
      <div className="text-gray-500 text-xs">{label}</div>
      <div className={`font-mono mt-0.5 tabular-nums text-sm ${accent ? 'text-amber-400' : 'text-gray-100'}`}>
        {value}
      </div>
    </div>
  )
}

const MAX_ENTRIES = 60

interface Props {
  sseState: SSEState
  perfMetrics: PerfMetrics
}

export function PerformanceLogs({ sseState, perfMetrics }: Props) {
  const [log, setLog] = useState<LogEntry[]>([])
  const tableRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (sseState.latencyMs === null || sseState.payloadBytes === null) return

    setLog((prev) =>
      [
        ...prev,
        {
          ts: Date.now(),
          latencyMs: sseState.latencyMs!,
          payloadBytes: sseState.payloadBytes!,
          fps: perfMetrics.fps,
          avgRenderMs: perfMetrics.avgRenderMs,
          frameDrops: perfMetrics.frameDrops,
        },
      ].slice(-MAX_ENTRIES),
    )
  }, [sseState.latencyMs, sseState.payloadBytes, perfMetrics])

  // Auto-scroll to newest entry
  useEffect(() => {
    if (tableRef.current) {
      tableRef.current.scrollTop = tableRef.current.scrollHeight
    }
  }, [log])

  const latencies = log.map((e) => e.latencyMs)
  const avgLatency = latencies.length ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : null
  const minLatency = latencies.length ? Math.min(...latencies) : null
  const maxLatency = latencies.length ? Math.max(...latencies) : null

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-200">Performance Monitor</h2>
      </div>

      {/* Summary grid */}
      <div className="grid grid-cols-4 gap-px bg-gray-800 border-b border-gray-800">
        <StatCard label="Avg latency" value={avgLatency !== null ? `${avgLatency}ms` : '—'} />
        <StatCard label="Min / Max" value={minLatency !== null ? `${minLatency} / ${maxLatency}ms` : '—'} />
        <StatCard label="FPS" value={perfMetrics.fps > 0 ? String(perfMetrics.fps) : '—'} />
        <StatCard label="Frame drops" value={String(perfMetrics.frameDrops)} accent={perfMetrics.frameDrops > 0} />
      </div>
      <div className="grid grid-cols-4 gap-px bg-gray-800 border-b border-gray-800">
        <StatCard label="TTI" value={perfMetrics.ttiMs !== null ? `${perfMetrics.ttiMs}ms` : '—'} />
        <StatCard label="Render avg" value={perfMetrics.avgRenderMs > 0 ? `${perfMetrics.avgRenderMs}ms` : '—'} />
        <StatCard label="Total renders" value={String(perfMetrics.renderCount)} />
        <StatCard label="Dropped events" value={String(sseState.droppedEvents)} accent={sseState.droppedEvents > 0} />
      </div>

      {/* Alert banners */}
      {sseState.recoveryMs !== null && (
        <div className="px-3 py-1.5 bg-emerald-950/40 border-b border-emerald-800/40 text-xs text-emerald-400">
          Last reconnection recovery: {sseState.recoveryMs}ms
        </div>
      )}
      {sseState.validationError && (
        <div className="px-3 py-1.5 bg-red-950/40 border-b border-red-800/40 text-xs text-red-400">
          Schema validation error: {sseState.validationError}
        </div>
      )}

      {/* Rolling event log */}
      <div ref={tableRef} className="overflow-y-auto" style={{ maxHeight: 200 }}>
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-gray-900/95">
            <tr className="text-gray-500">
              <th className="px-3 py-1.5 text-left font-normal">time</th>
              <th className="px-3 py-1.5 text-right font-normal">latency</th>
              <th className="px-3 py-1.5 text-right font-normal">bytes</th>
              <th className="px-3 py-1.5 text-right font-normal">fps</th>
              <th className="px-3 py-1.5 text-right font-normal">render</th>
            </tr>
          </thead>
          <tbody>
            {log.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-5 text-center text-gray-600">
                  Waiting for stream…
                </td>
              </tr>
            ) : (
              log.map((entry, i) => (
                <tr key={i} className="border-t border-gray-800/50 hover:bg-gray-800/20">
                  <td className="px-3 py-1 text-gray-600 tabular-nums">
                    {new Date(entry.ts).toLocaleTimeString([], { hour12: false })}
                  </td>
                  <td
                    className={`px-3 py-1 text-right tabular-nums ${
                      entry.latencyMs > 300
                        ? 'text-red-400'
                        : entry.latencyMs > 150
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {entry.latencyMs}ms
                  </td>
                  <td className="px-3 py-1 text-right text-gray-400 tabular-nums">{entry.payloadBytes}B</td>
                  <td className="px-3 py-1 text-right text-blue-400 tabular-nums">{entry.fps}</td>
                  <td className="px-3 py-1 text-right text-gray-400 tabular-nums">{entry.avgRenderMs.toFixed(1)}ms</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
