---
name: React frontend for turbofan dashboard
description: SSE streaming, react-window virtualization, Zod API contract; frontend/ replaces Streamlit
type: project
---

React frontend lives in `frontend/` (Vite + TypeScript + Tailwind, no Next.js).

**Key architectural decisions:**

- **SSE endpoint** added to `server.py` at `GET /stream/{engine_id}`. Streams one event per cycle from the CMAPSS test set. Each payload includes `inference_ts` (Unix ms) so the client can measure E2E latency as `Date.now() - inference_ts`. Also added `GET /engines` (list available engines) and CORS middleware.

- **Zod contract** in `src/api/schema.ts`. `RULEventSchema` mirrors the FastAPI payload exactly. `parseEvent()` returns a discriminated union so schema drift shows up as a visible UI error banner, not a silent undefined.

- **SSEClient** (`src/api/sseClient.ts`) is a plain class (not a hook) wrapping EventSource. Reconnection uses exponential backoff (1s × 2^attempt, max 30s). `BackpressureBuffer` is a bounded FIFO that evicts the oldest item when full — prevents unbounded queue growth if the UI stalls. `droppedCount` is cumulative.

- **useSSE** hook (`src/hooks/useSSE.ts`) owns the SSEClient lifecycle. Exposes `state` (status, latest event, latency, payload size, recovery time, validation errors) and `reset()`.

- **usePerfMonitor** hook (`src/hooks/usePerf.ts`) runs a `requestAnimationFrame` loop when active, sampling FPS every second. `trackRender(ms)` is called by `SensorPanel` after each render tick; TTI is set on first call.

- **SensorPanel** (`src/components/SensorPanel.tsx`) uses `react-window` `FixedSizeList` with `ROW_HEIGHT=40`. `SensorRow` has a custom `React.memo` comparator that skips re-render if `sensor.value` is unchanged (prevents scroll-triggered work on already-rendered rows).

- **PerformanceLogs** shows a live rolling table: E2E latency (coloured green/amber/red), payload bytes, FPS, render avg. Summary stats: avg/min/max latency, TTI, total renders, dropped events.

**Why:** Built for a frontend role resume — demonstrates real-time UI patterns (SSE, backpressure, reconnection), performance engineering (virtualisation, memoisation, rAF FPS), and full-stack type safety (Zod validates the FastAPI → React boundary).
