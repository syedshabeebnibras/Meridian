# Meridian Web — production-grade chat frontend

**Location**: `apps/web/` (new dir, separate from Python services)
**Stack**: Next.js 15.5 App Router · React 19 · TypeScript strict · Tailwind v4 · shadcn/ui · Framer Motion · Lucide · Zustand
**Deploy target**: Vercel (edge-compatible), dev via `pnpm dev` on :3001 (3000 is Langfuse)

---

## Architecture

```
Browser ──▶ Next.js /api/chat  (server-side proxy) ──▶ Orchestrator :8000 /v1/chat
       ◀── streaming or JSON  ◀────────────────────── ◀──
```

- Orchestrator URL is **server-only** (`ORCH_URL` env var, never NEXT_PUBLIC).
- Sessions persist via the orchestrator's Redis store. Client stores only a `session_id` in `localStorage` per conversation.
- Zustand store mirrors the conversation client-side for instant renders; source of truth is the orchestrator reply.

## Pages

1. `/` — marketing landing
   - Hero with animated gradient + dot-grid background
   - Live metric counters pulled from `/metrics` (requests served, avg latency, $ saved by cache)
   - Feature grid: Session memory · Rate limiter · Cost circuit breaker · Semantic cache · Observability · Tool actions
   - Architecture visualization (Phase diagram of state machine)
   - CTA → `/chat`

2. `/chat` — main product surface
   - Two-column layout: session sidebar (left, collapsible) + conversation pane (right)
   - Message list with virtualization-ready structure
   - Rich message bubbles:
     - **User**: right-aligned, gradient background
     - **Assistant**: left, with citation cards, insight panel (intent/tier/cost/latency/cache-hit badge), framer-motion entrance
     - **Cache hit**: special "⚡ Served from cache" badge + green accent
   - Input bar: auto-grow textarea, submit on Enter, Shift+Enter for newline, slash-commands hint
   - "Pipeline" indicator during pending: animated phase timeline (classify → retrieve → assemble → dispatch → validate)

3. `/docs` — embed Swagger UI from orchestrator

## Components (apps/web/components/)

- `ui/` — shadcn primitives (Button, Card, Dialog, Input, ScrollArea, Badge, Tooltip)
- `chat/MessageList.tsx`, `MessageBubble.tsx`, `CitationCard.tsx`, `InsightPanel.tsx`, `InputBar.tsx`, `SessionSidebar.tsx`, `PipelineIndicator.tsx`
- `landing/Hero.tsx`, `FeatureGrid.tsx`, `LiveMetrics.tsx`, `StateMachineViz.tsx`
- `shared/ThemeProvider.tsx`, `ThemeToggle.tsx`, `Logo.tsx`

## State (Zustand)

```ts
interface ChatStore {
  sessions: Record<string, Session>;
  activeSessionId: string;
  send: (query: string) => Promise<void>;
  newSession: () => void;
  deleteSession: (id: string) => void;
}
```

Persistence: `zustand/middleware/persist` to `localStorage` with a version key.

## API route

`app/api/chat/route.ts` — POST handler that:
1. Reads body + pulls `session_id` from cookies (or body).
2. Builds a `req_` ID matching the orchestrator regex `^req_[a-zA-Z0-9]+$`.
3. POSTs to `${process.env.ORCH_URL}/v1/chat` with an internal API key header.
4. Returns the orchestrator JSON, or surfaces 429 with its Retry-After header.

## Styling

- Tailwind v4 CSS-first tokens in `app/globals.css`:
  - Inter font for body, JetBrains Mono for code
  - Semantic colors: `--color-bg`, `--color-fg`, `--color-accent`, `--color-muted`, ...
  - Dark mode via `class="dark"` on `<html>` (default dark)
- Background: radial gradient + SVG dot grid overlay at 10% opacity
- Shadows: subtle, layered (shadcn palette)

## Animations (Framer Motion)

- Message entrance: `opacity 0 → 1, y 8 → 0, 0.3s ease-out`
- Pipeline phases: stroke-dasharray draw-on for each phase as it completes
- Cache hit: scale + glow pulse on the "cache" badge for 600ms
- Intent pill: color shift based on classification (grounded_qa=blue, tool_action=violet, out_of_scope=rose)
- Sidebar collapse: width + opacity transition
- Landing hero: looping gradient shift

## Files to create

```
apps/web/
  package.json
  tsconfig.json
  next.config.ts
  tailwind.config.ts      (v4 still needs it for content paths)
  postcss.config.mjs
  components.json         (shadcn)
  .env.local.example
  app/
    layout.tsx
    page.tsx              (landing)
    globals.css
    chat/
      page.tsx
      layout.tsx
    api/
      chat/route.ts
      metrics/route.ts
  components/
    ui/                   (shadcn primitives)
    chat/
    landing/
    shared/
  lib/
    orchestrator.ts       (fetch wrapper, typed)
    store.ts              (zustand)
    utils.ts              (cn helper)
    types.ts              (mirror of orchestrator types)
  public/
    favicon.svg
    logo.svg
```

## Build steps

1. Scaffold Next.js 15 + TypeScript in `apps/web/`
2. Install deps: tailwindcss@4, framer-motion, lucide-react, zustand, clsx, tailwind-merge
3. Install shadcn primitives we need: Button, Card, Input, ScrollArea, Badge, Separator, Tooltip, Dialog
4. Theme system + globals.css with design tokens
5. Core layout + ThemeProvider
6. Lib: orchestrator.ts, store.ts, types.ts
7. API route `/api/chat`
8. Landing page
9. Chat page + components
10. Framer Motion animations
11. Responsive polish (mobile → desktop breakpoints)
12. `.env.local.example`, README section, `vercel.json`

## Dev workflow

- `cd apps/web && pnpm install`
- `pnpm dev` → http://localhost:3001
- Orchestrator must be running on :8000 (or `ORCH_URL` set)

---

## Acceptance

- [ ] Landing page renders with animated hero + feature grid
- [ ] /chat page sends real requests, receives real responses, displays citations + insight panel
- [ ] Session memory works across page reloads (localStorage + Redis)
- [ ] Cache-hit indicator appears when orchestrator returns `model="cache"`
- [ ] 429 from orchestrator surfaces as toast with retry timer
- [ ] Dark mode default, light toggle works
- [ ] Mobile responsive (≥360px)
- [ ] `pnpm build` succeeds (0 TS errors)
- [ ] Lighthouse score ≥ 95 on landing
