import React from 'react'
import type { ConnectionStatus as Status } from '../hooks/useSSE'

interface Props {
  status: Status
  engineId: string | null
  reconnectAttempt: number
  reconnectDelayMs: number | null
  recoveryMs: number | null
}

const CONFIG: Record<Status, { label: string; dot: string; text: string }> = {
  idle:         { label: 'Idle',             dot: 'bg-gray-500',                   text: 'text-gray-400'   },
  connecting:   { label: 'Connecting',       dot: 'bg-yellow-400 animate-pulse',   text: 'text-yellow-400' },
  connected:    { label: 'Live',             dot: 'bg-emerald-400 animate-pulse',  text: 'text-emerald-400'},
  reconnecting: { label: 'Reconnecting',     dot: 'bg-orange-400 animate-ping',    text: 'text-orange-400' },
  disconnected: { label: 'Disconnected',     dot: 'bg-red-500',                    text: 'text-red-500'    },
  done:         { label: 'Stream Complete',  dot: 'bg-blue-400',                   text: 'text-blue-400'   },
}

export const ConnectionStatus = React.memo(function ConnectionStatus({
  status,
  engineId,
  reconnectAttempt,
  reconnectDelayMs,
  recoveryMs,
}: Props) {
  const cfg = CONFIG[status]

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${cfg.dot}`} />
      <span className={`text-sm font-medium ${cfg.text}`}>{cfg.label}</span>

      {engineId && (
        <span className="text-sm text-gray-400">
          — <span className="font-mono text-gray-200">{engineId}</span>
        </span>
      )}

      {status === 'reconnecting' && reconnectDelayMs !== null && (
        <span className="text-xs text-orange-300">
          (attempt {reconnectAttempt}, retry in {(reconnectDelayMs / 1_000).toFixed(1)}s)
        </span>
      )}

      {recoveryMs !== null && status === 'connected' && (
        <span className="text-xs text-emerald-300">recovered in {recoveryMs}ms</span>
      )}
    </div>
  )
})
