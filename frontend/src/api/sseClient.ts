import { z } from 'zod'
import { parseEvent } from './schema'

// ── Backpressure buffer ───────────────────────────────────────────────────────
// Bounded FIFO queue. When the consumer can't keep up with the producer,
// the oldest item is evicted and droppedCount is incremented rather than
// letting the queue grow without bound.
//
// In a single-threaded JS runtime EventSource fires messages sequentially,
// so the queue depth is normally ≤1. The buffer exists as an explicit
// defence for bursts (e.g. rapid reconnects replaying buffered events).

export class BackpressureBuffer<T> {
  private queue: T[] = []
  droppedCount = 0

  constructor(private readonly maxSize: number = 10) {}

  push(item: T): void {
    if (this.queue.length >= this.maxSize) {
      this.queue.shift() // evict oldest
      this.droppedCount++
    }
    this.queue.push(item)
  }

  drain(): T[] {
    const items = this.queue
    this.queue = []
    return items
  }

  get size(): number {
    return this.queue.length
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MessageMeta {
  /** performance.now() at EventSource message handler invocation */
  receivedAt: number
  /** Date.now() - inference_ts: wall-clock E2E latency including network + parse */
  latencyMs: number
  /** Serialised SSE event payload size in bytes */
  payloadBytes: number
}

export interface SSEClientOptions<T> {
  url: string
  schema: z.ZodSchema<T>
  onMessage: (data: T, meta: MessageMeta) => void
  onValidationError?: (error: string, raw: unknown) => void
  onConnect?: () => void
  onDisconnect?: (attempt: number) => void
  /** Fired just before a reconnect attempt with the backoff delay in ms */
  onReconnect?: (attempt: number, delayMs: number) => void
  /** Fired on successful reconnection with elapsed ms since disconnect */
  onRecovered?: (recoveryMs: number) => void
  onDone?: () => void
  maxQueueSize?: number
  /** undefined = retry forever */
  maxRetries?: number
  initialDelayMs?: number
  maxDelayMs?: number
}

// ── SSEClient ─────────────────────────────────────────────────────────────────

export class SSEClient<T extends { inference_ts: number }> {
  private es: EventSource | null = null
  private closed = false
  private attempt = 0
  private disconnectedAt: number | null = null // performance.now() timestamp
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private buffer: BackpressureBuffer<T>

  constructor(private readonly opts: SSEClientOptions<T>) {
    this.buffer = new BackpressureBuffer(opts.maxQueueSize ?? 10)
    this.open()
  }

  private open(): void {
    if (this.closed) return

    this.es = new EventSource(this.opts.url)

    this.es.onopen = () => {
      const now = performance.now()

      if (this.disconnectedAt !== null) {
        const recoveryMs = Math.round(now - this.disconnectedAt)
        this.opts.onRecovered?.(recoveryMs)
        console.info(`[SSE] recovered in ${recoveryMs}ms after ${this.attempt} attempt(s)`)
      }

      this.attempt = 0
      this.disconnectedAt = null
      this.opts.onConnect?.()
    }

    this.es.onmessage = (ev: MessageEvent<string>) => {
      const receivedAt = performance.now()
      const payloadBytes = new TextEncoder().encode(ev.data).byteLength

      let parsed: unknown
      try {
        parsed = JSON.parse(ev.data)
      } catch {
        this.opts.onValidationError?.('JSON parse failed', ev.data)
        return
      }

      const result = parseEvent(this.opts.schema, parsed)
      if (!result.ok) {
        this.opts.onValidationError?.(result.error, parsed)
        return
      }

      const data = result.data
      // E2E latency: server stamped inference_ts as Unix ms, client uses Date.now()
      const latencyMs = Date.now() - data.inference_ts
      const meta: MessageMeta = { receivedAt, latencyMs, payloadBytes }

      this.buffer.push(data)

      // Drain immediately. Under backpressure push() already dropped the oldest
      // item and incremented droppedCount — we never process stale data.
      for (const item of this.buffer.drain()) {
        this.opts.onMessage(item, meta)
      }
    }

    // Server signals clean stream end via a named 'done' event
    this.es.addEventListener('done', () => {
      this.opts.onDone?.()
      this.close()
    })

    this.es.onerror = () => {
      if (this.closed) return

      if (this.disconnectedAt === null) {
        this.disconnectedAt = performance.now()
      }

      this.es?.close()
      this.es = null

      const { maxRetries } = this.opts
      if (maxRetries !== undefined && this.attempt >= maxRetries) {
        console.warn(`[SSE] giving up after ${this.attempt} retries`)
        this.opts.onDisconnect?.(this.attempt)
        return
      }

      // Exponential backoff with jitter: delay = base * 2^attempt, capped
      const base = this.opts.initialDelayMs ?? 1_000
      const cap = this.opts.maxDelayMs ?? 30_000
      const delay = Math.min(base * 2 ** this.attempt, cap)

      this.opts.onDisconnect?.(this.attempt)
      this.opts.onReconnect?.(this.attempt + 1, delay)
      console.info(`[SSE] reconnecting in ${delay}ms (attempt ${this.attempt + 1})`)

      this.attempt++
      this.retryTimer = setTimeout(() => this.open(), delay)
    }
  }

  close(): void {
    this.closed = true
    if (this.retryTimer !== null) clearTimeout(this.retryTimer)
    this.es?.close()
    this.es = null
  }

  get droppedCount(): number {
    return this.buffer.droppedCount
  }
}
