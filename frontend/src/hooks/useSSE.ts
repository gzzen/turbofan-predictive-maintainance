import { useCallback, useEffect, useRef, useState } from 'react'
import { SSEClient, type MessageMeta } from '../api/sseClient'
import { RULEventSchema, type RULEvent } from '../api/schema'

export type ConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'done'

export interface SSEState {
  status: ConnectionStatus
  latest: RULEvent | null
  /** Wall-clock E2E latency for the last event (ms) */
  latencyMs: number | null
  /** Serialised payload size for the last event (bytes) */
  payloadBytes: number | null
  /** ms elapsed between disconnect and successful reconnect */
  recoveryMs: number | null
  reconnectAttempt: number
  reconnectDelayMs: number | null
  validationError: string | null
  /** Total events dropped by the backpressure buffer */
  droppedEvents: number
}

const INITIAL: SSEState = {
  status: 'idle',
  latest: null,
  latencyMs: null,
  payloadBytes: null,
  recoveryMs: null,
  reconnectAttempt: 0,
  reconnectDelayMs: null,
  validationError: null,
  droppedEvents: 0,
}

export function useSSE(engineId: string | null, streamInterval = 1.0) {
  const [state, setState] = useState<SSEState>(INITIAL)
  const clientRef = useRef<SSEClient<RULEvent> | null>(null)

  const reset = useCallback(() => {
    clientRef.current?.close()
    clientRef.current = null
    setState(INITIAL)
  }, [])

  useEffect(() => {
    if (!engineId) return

    setState({ ...INITIAL, status: 'connecting' })

    const url = `/stream/${encodeURIComponent(engineId)}?interval=${streamInterval}`

    clientRef.current = new SSEClient<RULEvent>({
      url,
      schema: RULEventSchema,

      onConnect: () =>
        setState((s) => ({
          ...s,
          status: 'connected',
          reconnectAttempt: 0,
          reconnectDelayMs: null,
        })),

      onDisconnect: (attempt) =>
        setState((s) => ({ ...s, status: 'reconnecting', reconnectAttempt: attempt })),

      onReconnect: (attempt, delayMs) =>
        setState((s) => ({ ...s, status: 'reconnecting', reconnectAttempt: attempt, reconnectDelayMs: delayMs })),

      onRecovered: (recoveryMs) =>
        setState((s) => ({ ...s, status: 'connected', recoveryMs })),

      onDone: () =>
        setState((s) => ({ ...s, status: 'done' })),

      onValidationError: (error) =>
        setState((s) => ({ ...s, validationError: error })),

      onMessage: (data: RULEvent, meta: MessageMeta) =>
        setState((s) => ({
          ...s,
          latest: data,
          latencyMs: meta.latencyMs,
          payloadBytes: meta.payloadBytes,
          droppedEvents: clientRef.current?.droppedCount ?? s.droppedEvents,
          validationError: null,
        })),

      maxQueueSize: 8,
      initialDelayMs: 1_000,
      maxDelayMs: 30_000,
    })

    return () => {
      clientRef.current?.close()
      clientRef.current = null
    }
  }, [engineId, streamInterval])

  return { state, reset }
}
