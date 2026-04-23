import { z } from 'zod'

// ── SSE event schema ──────────────────────────────────────────────────────────
// Mirrors FastAPI's streaming payload exactly.
// Every incoming event is validated at the boundary so schema drift surfaces
// as an actionable UI error rather than a silent NaN or undefined read.

export const RULEventSchema = z.object({
  engine_id: z.string(),
  cycle: z.number().int().nonnegative(),
  total_cycles: z.number().int().positive(),
  predicted_rul: z.number(),
  maintenance_advisory: z.boolean(),
  threshold_cycles: z.number().int().positive(),
  // s_1 … s_21 as a record — regex guards against extra noise keys
  sensors: z.record(z.string().regex(/^s_\d{1,2}$/), z.number()),
  // Unix ms at server inference completion; client subtracts Date.now() for E2E latency
  inference_ts: z.number().int(),
  inference_duration_ms: z.number(),
})

export type RULEvent = z.infer<typeof RULEventSchema>

// ── REST schemas ──────────────────────────────────────────────────────────────

export const HealthSchema = z.object({
  status: z.string(),
  model_loaded: z.boolean(),
  run_id: z.string().nullable().optional(),
})

export type Health = z.infer<typeof HealthSchema>

export const EngineListSchema = z.object({
  dataset: z.string(),
  engines: z.array(z.string()),
})

export type EngineList = z.infer<typeof EngineListSchema>

// ── Validation helper ─────────────────────────────────────────────────────────

export type ParseResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string }

export function parseEvent<T>(schema: z.ZodSchema<T>, raw: unknown): ParseResult<T> {
  const result = schema.safeParse(raw)
  if (result.success) return { ok: true, data: result.data }
  return {
    ok: false,
    error: result.error.issues
      .map((i) => `${i.path.join('.')}: ${i.message}`)
      .join('; '),
  }
}
