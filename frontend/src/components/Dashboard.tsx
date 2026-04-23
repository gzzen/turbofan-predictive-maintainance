import React, { useState } from 'react'
import { useSSE } from '../hooks/useSSE'
import { usePerfMonitor } from '../hooks/usePerf'
import { ConnectionStatus } from './ConnectionStatus'
import { RULGauge } from './RULGauge'
import { SensorPanel } from './SensorPanel'
import { PerformanceLogs } from './PerformanceLogs'

const ENGINES = Array.from({ length: 10 }, (_, i) => `engine_${i + 1}`)

export function Dashboard() {
  const [selectedEngine, setSelectedEngine] = useState('engine_1')
  const [activeEngine, setActiveEngine] = useState<string | null>(null)
  const [streamInterval, setStreamInterval] = useState(1.0)

  const { state, reset } = useSSE(activeEngine, streamInterval)
  const { metrics, trackRender } = usePerfMonitor(activeEngine !== null)

  const latest = state.latest
  const isRunning = activeEngine !== null

  function handleStart() {
    reset()
    setActiveEngine(selectedEngine)
  }

  function handleStop() {
    reset()
    setActiveEngine(null)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-gray-950/90 backdrop-blur border-b border-gray-800 px-6 py-3 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-base font-semibold tracking-tight">
            Turbofan Predictive Maintenance
          </h1>
          <p className="text-xs text-gray-500">CMAPSS · SSE · react-window · Zod</p>
        </div>
        <ConnectionStatus
          status={state.status}
          engineId={activeEngine}
          reconnectAttempt={state.reconnectAttempt}
          reconnectDelayMs={state.reconnectDelayMs}
          recoveryMs={state.recoveryMs}
        />
      </header>

      {/* ── Controls ───────────────────────────────────────────────────────── */}
      <div className="px-6 py-3 border-b border-gray-800 flex items-center gap-4 flex-wrap bg-gray-950">
        <label className="flex items-center gap-2 text-sm text-gray-400">
          Engine
          <select
            value={selectedEngine}
            onChange={(e) => setSelectedEngine(e.target.value)}
            disabled={isRunning}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 text-sm
                       disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            {ENGINES.map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 text-sm text-gray-400">
          Interval (s)
          <input
            type="number"
            value={streamInterval}
            onChange={(e) => setStreamInterval(Math.max(0.1, Number(e.target.value)))}
            disabled={isRunning}
            min={0.1}
            step={0.1}
            className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 text-sm
                       disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-600"
          />
        </label>

        {!isRunning ? (
          <button
            onClick={handleStart}
            className="px-4 py-1.5 rounded bg-blue-600 hover:bg-blue-500 active:bg-blue-700
                       text-sm font-medium transition-colors"
          >
            Start Stream
          </button>
        ) : (
          <button
            onClick={handleStop}
            className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 active:bg-gray-800
                       text-sm font-medium transition-colors"
          >
            Stop
          </button>
        )}

        {state.status === 'done' && (
          <span className="text-xs text-blue-400">
            Stream finished — {latest?.total_cycles} cycles replayed
          </span>
        )}
      </div>

      {/* ── Main layout ────────────────────────────────────────────────────── */}
      <main className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

        {/* ── Left: RUL gauge + inference metadata ─────────────────────── */}
        <div className="flex flex-col gap-4">
          <div className="rounded-xl bg-gray-900 border border-gray-800 p-5 flex flex-col items-center">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4 self-start">
              Remaining Useful Life
            </h2>
            <RULGauge
              rul={latest?.predicted_rul ?? null}
              thresholdCycles={latest?.threshold_cycles ?? 30}
              cycle={latest?.cycle ?? null}
              totalCycles={latest?.total_cycles ?? null}
              maintenanceAdvisory={latest?.maintenance_advisory ?? false}
            />
          </div>

          {/* Inference metadata */}
          <div className="rounded-xl bg-gray-900 border border-gray-800 p-4 space-y-2">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Inference
            </h2>
            {(
              [
                ['Engine',          latest?.engine_id ?? '—'],
                ['Cycle',           latest?.cycle !== undefined ? String(latest.cycle) : '—'],
                ['Server inference', latest?.inference_duration_ms !== undefined
                                      ? `${latest.inference_duration_ms}ms` : '—'],
                ['E2E latency',     state.latencyMs !== null ? `${state.latencyMs}ms` : '—'],
                ['Payload',         state.payloadBytes !== null ? `${state.payloadBytes}B` : '—'],
              ] as [string, string][]
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between text-xs font-mono">
                <span className="text-gray-500">{label}</span>
                <span className="text-gray-200 tabular-nums">{value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Middle: virtualised sensor panel ─────────────────────────── */}
        <div>
          <SensorPanel latest={latest} onRenderTime={trackRender} />
        </div>

        {/* ── Right: performance logs ───────────────────────────────────── */}
        <div>
          <PerformanceLogs sseState={state} perfMetrics={metrics} />
        </div>
      </main>
    </div>
  )
}
