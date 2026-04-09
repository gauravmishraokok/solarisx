import { create } from 'zustand'

const LAYOUT_KEY_LEFT = 'memora_layout_left'
const LAYOUT_KEY_BOTTOM = 'memora_layout_bottom'

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n))
}

function readLayoutLeft() {
  if (typeof localStorage === 'undefined') return 320
  const s = localStorage.getItem(LAYOUT_KEY_LEFT)
  return s ? clamp(parseInt(s, 10) || 320, 220, 560) : 320
}

function readLayoutBottom() {
  if (typeof localStorage === 'undefined') return 220
  const s = localStorage.getItem(LAYOUT_KEY_BOTTOM)
  return s ? clamp(parseInt(s, 10) || 220, 120, 560) : 220
}

interface UIState {
  bottomTab: 'graph' | 'timeline' | 'health'
  isBottomOpen: boolean
  leftPanelWidth: number
  bottomPanelHeight: number
  memoryFilter: Set<string>
  selectedNodeId: string | null
  flashedMemoryIds: string[]
  setBottomTab: (t: UIState['bottomTab']) => void
  toggleBottom: () => void
  setLeftPanelWidth: (w: number) => void
  setBottomPanelHeight: (h: number) => void
  toggleFilter: (type: string) => void
  selectNode: (id: string | null) => void
  flashMemories: (ids: string[]) => void
}

export const useUIStore = create<UIState>((set) => ({
  bottomTab: 'graph',
  isBottomOpen: true,
  leftPanelWidth: readLayoutLeft(),
  bottomPanelHeight: readLayoutBottom(),
  memoryFilter: new Set<string>(),
  selectedNodeId: null,
  flashedMemoryIds: [],

  setBottomTab: (t) => set({ bottomTab: t }),
  toggleBottom: () => set((s) => ({ isBottomOpen: !s.isBottomOpen })),

  setLeftPanelWidth: (w) => {
    const nw = clamp(w, 220, 560)
    try {
      localStorage.setItem(LAYOUT_KEY_LEFT, String(nw))
    } catch {
      /* ignore */
    }
    set({ leftPanelWidth: nw })
  },

  setBottomPanelHeight: (h) => {
    const nh = clamp(h, 120, 560)
    try {
      localStorage.setItem(LAYOUT_KEY_BOTTOM, String(nh))
    } catch {
      /* ignore */
    }
    set({ bottomPanelHeight: nh })
  },

  toggleFilter: (type) =>
    set((s) => {
      const next = new Set(s.memoryFilter)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return { memoryFilter: next }
    }),

  selectNode: (id) => set({ selectedNodeId: id }),

  flashMemories: (ids) => {
    set({ flashedMemoryIds: ids })
    setTimeout(() => set({ flashedMemoryIds: [] }), 2000)
  },
}))
