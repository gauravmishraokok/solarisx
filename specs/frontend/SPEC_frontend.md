# SPEC: frontend/ — React + D3 + Tailwind Frontend

## Module Purpose
The "wow factor" presentation layer. Four-panel dark dashboard that makes the hackathon judges remember MEMORA.
Aesthetic: Neural terminal meets legal brief. Dark base, monospace for memory content, sharp serif headings.

---

# SPEC: frontend/vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
```

---

# SPEC: frontend/src/styles/globals.css

## CSS Variables (Design Tokens)

```css
:root {
  /* Base palette — dark neural terminal */
  --color-bg:          #0a0b0f;
  --color-surface:     #111318;
  --color-surface-2:   #1a1d24;
  --color-border:      #2a2d36;
  --color-border-dim:  #1e2028;

  /* Text */
  --color-text-primary:   #e8eaf0;
  --color-text-secondary: #8891a8;
  --color-text-dim:       #4a5168;

  /* Accent system */
  --color-accent:      #4f9cf8;   /* Electric blue — active memories */
  --color-warn:        #f5a623;   /* Amber — quarantine/contradiction */
  --color-danger:      #f25f5c;   /* Red — deprecated/conflict */
  --color-success:     #50fa7b;   /* Green — approved/resolved */
  --color-neutral:     #6272a4;   /* Muted blue-grey */

  /* Memory type colors */
  --color-episodic:    #bd93f9;   /* Purple */
  --color-semantic:    #4f9cf8;   /* Blue */
  --color-kg-node:     #50fa7b;   /* Green */
  --color-kg-edge:     #ffb86c;   /* Orange */

  /* Tier colors */
  --color-hot:         #ff5555;
  --color-warm:        #f1fa8c;
  --color-cold:        #6272a4;

  /* Typography */
  --font-display:  'DM Serif Display', Georgia, serif;
  --font-body:     'IBM Plex Sans', system-ui, sans-serif;
  --font-mono:     'JetBrains Mono', 'Fira Code', monospace;
}
```

Google Fonts to load: `DM Serif Display`, `IBM Plex Sans`, `JetBrains Mono`

---

# SPEC: frontend/src/components/layout/Shell.tsx

## Purpose
4-panel responsive dashboard layout. The master layout component.

## Layout Grid

```
┌─────────────────────────────────────────────────────────────┐
│  TopBar (fixed, 56px)                                        │
├────────────────────┬──────────────────────────┬─────────────┤
│  Left Panel (30%)  │  Center Panel (40%)       │ Right (30%) │
│  KnowledgeGraph    │  ChatPanel                │ CourtDash   │
│                    │                           │             │
├────────────────────┴──────────────────────────┴─────────────┤
│  Bottom Panel (200px, collapsible)                           │
│  MemoryTimeline + HealthPanel                                │
└─────────────────────────────────────────────────────────────┘
```

**Behaviour:**
- On mobile (< 768px): stack panels vertically with tab navigation
- Bottom panel: collapsible via toggle button
- Each panel scrolls independently

---

# SPEC: frontend/src/components/layout/TopBar.tsx

```
[MEMORA]  Session: abc-123  ●  3 Memories  ⚠ 1 Pending  |  [New Session]
```

Elements:
- Logo: "MEMORA" in `--font-display`, size 1.4rem
- Session ID: monospace, truncated to 8 chars + "..."
- Status dot: green (active) / amber (pending contradictions) / red (error)
- Memory count badge
- Pending quarantine badge (hidden if 0)
- "New Session" button

---

# SPEC: frontend/src/components/chat/ChatPanel.tsx

## Purpose
Main conversation interface. Left-to-right message bubbles.

## State (from `chatStore`):
- `messages: Message[]`
- `inputValue: string`
- `isLoading: boolean`
- `sessionId: string | null`

## Layout:
```
┌──────────────────────────────────┐
│ CHAT                             │
│ [Memory badge: pricing, B2B]     │
├──────────────────────────────────┤
│                                  │
│   [User message bubble]          │
│          [Agent response]        │
│   [User message bubble]          │
│          [Agent response]        │
│                                  │
├──────────────────────────────────┤
│ [Input field]          [Send ▶]  │
│ [👍 Good] [👎 Bad]              │
└──────────────────────────────────┘
```

## Key Behaviours:
- Send on Enter (Shift+Enter for newline)
- After each agent response, show memory badges (MemoryBadge components) listing the cube IDs used
- 👍 / 👎 buttons visible after each agent response; clicking 👎 prompts for feedback text, then sends `feedback` field in next `/chat` call
- Auto-scroll to bottom on new message
- Show typing indicator (animated dots) while `isLoading`

---

# SPEC: frontend/src/components/chat/MemoryBadge.tsx

Small pill showing a memory cube was used in a response.

```tsx
// Example output:
// [episodic] pricing-strategy   [semantic] user-preference
```

Props:
```typescript
interface MemoryBadgeProps {
  cubeId: string
  memoryType: 'episodic' | 'semantic' | 'kg_node'
  content?: string   // Short preview on hover
}
```

Color: uses `--color-episodic`, `--color-semantic`, `--color-kg-node` per type.

---

# SPEC: frontend/src/components/graph/KnowledgeGraph.tsx

## Purpose
D3.js force-directed graph. The most visually impressive component.

## Props:
```typescript
interface KnowledgeGraphProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  onNodeClick: (nodeId: string) => void
}

interface GraphNode {
  id: string
  label: string      // Short display name (first 30 chars of content)
  type: 'episodic' | 'semantic' | 'kg_node'
  tier: 'hot' | 'warm' | 'cold'
}

interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  active: boolean   // active=false → render as dashed red line
}
```

## D3 Implementation Notes:

```javascript
// Force simulation config:
const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(edges).id(d => d.id).distance(120))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(width/2, height/2))
  .force("collision", d3.forceCollide().radius(40))

// Node visual encoding:
// - Size: tier=HOT → r=12, WARM → r=9, COLD → r=6
// - Color: var(--color-{type}) from CSS variables
// - Glow: HOT nodes get drop-shadow filter

// Edge visual encoding:
// - Active edges: solid line, color var(--color-border)
// - Deprecated edges: dashed line, color var(--color-danger), opacity 0.4
```

## Interactions:
- **Hover node:** Show `NodeTooltip` with content preview + version history
- **Click node:** Emit `onNodeClick`, highlights connected edges
- **Zoom/pan:** D3 zoom behavior, [0.3, 5] zoom range
- **New node animation:** nodes animate in from center on data update

---

# SPEC: frontend/src/components/court/CourtDashboard.tsx

## Purpose
Live feed of quarantine queue. The most interactive demo component.

## Layout:
```
┌────────────────────────────────────────────────────────┐
│  MEMORY COURT   ⚠ 2 Pending                            │
├─────────────────────────────────────────────────────────┤
│  [ContradictionCard]                                    │
│  [ContradictionCard]                                    │
│  [Empty state: "All memories approved ✓"]              │
└─────────────────────────────────────────────────────────┘
```

Polls `/court/queue` every 3 seconds.
When queue changes from 0 → N, play a subtle pulse animation on the panel border.

---

# SPEC: frontend/src/components/court/ContradictionCard.tsx

## The most important UI card in the demo.

## Layout:
```
┌──────────────────────────────────────────────────────────┐
│  Score: ████████░░  0.85         [Quarantine #abc-123]   │
├──────────────────┬───────────────────────────────────────┤
│  INCOMING        │  CONFLICTS WITH                        │
│  "User prefers   │  "User prefers low-cost B2B pricing"  │
│  premium pricing │                                        │
│  strategy"       │                                        │
├──────────────────┴───────────────────────────────────────┤
│  Reasoning: Both memories make conflicting claims about  │
│  the user's pricing preference...                        │
├──────────────────────────────────────────────────────────┤
│  Suggestion: reject                                      │
│  [✓ Accept] [✗ Reject] [⟳ Merge...]                     │
└──────────────────────────────────────────────────────────┘
```

Props:
```typescript
interface ContradictionCardProps {
  item: QuarantineItemResponse
  onResolve: (quarantineId: string, resolution: string, mergedContent?: string) => void
}
```

"Merge..." opens `ResolveModal`.

---

# SPEC: frontend/src/components/court/ScoreGauge.tsx

## Purpose
Visual arc gauge showing contradiction score.

```
     0.85
  ┌───────┐
  │  ████ │    Arc from 0° to 306° (representing 0.0 to 1.0)
  │       │    Color: gradient from green (0) to amber (0.6) to red (0.75+)
  └───────┘
```

Implemented as SVG arc. No external chart library needed.

Props:
```typescript
interface ScoreGaugeProps {
  score: number    // 0.0 to 1.0
  threshold: number // Default 0.75 — shown as marker line
}
```

Color: below threshold → amber, above threshold → red.

---

# SPEC: frontend/src/components/court/ResolveModal.tsx

Modal for "Merge" resolution.

```
┌────────────────────────────────────┐
│  Merge Memories                    │
│                                    │
│  Edit merged content:              │
│  ┌──────────────────────────────┐  │
│  │ [Pre-filled with suggestion] │  │
│  └──────────────────────────────┘  │
│                                    │
│         [Cancel]  [Confirm Merge]  │
└────────────────────────────────────┘
```

---

# SPEC: frontend/src/components/timeline/MemoryTimeline.tsx

## Purpose
Horizontal scrollable timeline of memory events.

## Visual:
```
created    updated    quarantined  resolved   created    evicted
  │           │            │          │          │          │
──●───────────●────────────●──────────●──────────●──────────●──→ time
 10:23      10:31        10:45      10:47      10:52      11:01
```

- Each event is a `TimelineEvent` component
- Color-coded by `event_type`:
  - created → `--color-success`
  - updated → `--color-accent`
  - quarantined → `--color-warn`
  - resolved → `--color-success`
  - evicted → `--color-text-dim`
- Click event → highlights the corresponding memory in KnowledgeGraph

---

# SPEC: frontend/src/components/health/HealthPanel.tsx

## Purpose
4 metric cards + 1 tier distribution bar.

## Cards:
1. **Total Memories** — integer count, trend arrow
2. **Retrieval Latency** — "p50: 42ms / p99: 180ms"
3. **Quarantine Pending** — integer, amber if > 0
4. **Memory Age** — "Newest: 2m ago"

## TierChart:
Horizontal stacked bar:
```
HOT ████ 12%   WARM ████████████████ 68%   COLD █████ 20%
```

---

# SPEC: frontend/src/hooks/

## useCourtQueue.ts
```typescript
export function useCourtQueue() {
  // Polls GET /api/court/queue every 3000ms
  // Returns: { queue: QuarantineItemResponse[], isLoading, error }
  // Uses React Query with refetchInterval: 3000
}
```

## useGraphData.ts
```typescript
export function useGraphData() {
  // Fetches GET /api/graph/nodes and GET /api/graph/edges in parallel
  // Refetches on window focus (D3 graph updates when new memories arrive)
  // Returns: { nodes, edges, isLoading, error }
}
```

## useHealth.ts
```typescript
export function useHealth() {
  // Polls GET /api/health every 5000ms
  // Returns health metrics
}
```

## useTimeline.ts
```typescript
export function useTimeline(sessionId: string | null) {
  // Fetches GET /api/timeline?session_id={sessionId}&limit=50
  // Refetches on focus
}
```

## useMemories.ts
```typescript
export function useMemories(sessionId: string | null) {
  // Fetches GET /api/memories?session_id={sessionId}
  // Provides: memories, searchMemories(query), deleteMemory(id)
}
```

---

# SPEC: frontend/src/store/

## chatStore.ts (Zustand)
```typescript
interface ChatState {
  messages: Message[]
  sessionId: string | null
  isLoading: boolean
  addMessage: (msg: Message) => void
  setSession: (id: string) => void
  setLoading: (v: boolean) => void
  clear: () => void
}
```

## courtStore.ts (Zustand)
```typescript
interface CourtState {
  activeResolutionId: string | null   // Which quarantine card is open for resolution
  setActiveResolution: (id: string | null) => void
}
```

## uiStore.ts (Zustand)
```typescript
interface UIState {
  activePanel: 'graph' | 'timeline' | 'health'
  isBottomPanelOpen: boolean
  selectedNodeId: string | null
  setActivePanel: (panel: UIState['activePanel']) => void
  toggleBottomPanel: () => void
  selectNode: (id: string | null) => void
}
```

---

# Frontend "Done" Criteria

- [ ] All 4 panels visible at once on 1440px width monitor
- [ ] D3 graph renders with > 0 nodes after first chat message
- [ ] ContradictionCard appears within 3 seconds of a quarantine event
- [ ] Resolve buttons successfully call `/court/resolve/{id}`
- [ ] Timeline scrolls and shows events colored by type
- [ ] Health panel shows live memory count
- [ ] Chat input → response cycle completes without page refresh
- [ ] MemoryBadge appears on each agent response showing which memories were used
