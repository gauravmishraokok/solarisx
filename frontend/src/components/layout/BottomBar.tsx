import React from 'react'
import { useUIStore } from '../../store'
import { KnowledgeGraph } from '../graph/KnowledgeGraph'
import { MemoryTimeline } from '../timeline/MemoryTimeline'
import { HealthPanel } from '../health/HealthPanel'

const TABS: { id: 'graph' | 'timeline' | 'health'; label: string }[] = [
  { id: 'graph', label: '⬡ Knowledge Graph' },
  { id: 'timeline', label: '≡ Timeline' },
  { id: 'health', label: '◈ System Health' },
]

export function BottomBar() {
  const { bottomTab, isBottomOpen, bottomPanelHeight, setBottomTab, toggleBottom } = useUIStore()

  return (
    <div
      className={`bottom-bar ${isBottomOpen ? 'open' : 'closed'}`}
      style={isBottomOpen ? { height: bottomPanelHeight } : { height: 40 }}
    >
      {/* Tab bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        borderBottom: isBottomOpen ? '1px solid var(--border-dim)' : 'none',
        padding: '0 16px',
        height: 40,
        gap: 0,
        flexShrink: 0,
      }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setBottomTab(tab.id); if (!isBottomOpen) toggleBottom() }}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: bottomTab === tab.id && isBottomOpen
                ? '2px solid var(--accent-blue)'
                : '2px solid transparent',
              color: bottomTab === tab.id && isBottomOpen
                ? 'var(--accent-blue)'
                : 'var(--text-dim)',
              fontFamily: 'var(--font-display)',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.06em',
              padding: '0 16px',
              height: '100%',
              cursor: 'pointer',
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}

        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={toggleBottom}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-base)',
              borderRadius: 4,
              color: 'var(--text-dim)',
              padding: '2px 10px',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            {isBottomOpen ? '▼' : '▲'}
          </button>
        </div>
      </div>

      {/* Content */}
      {isBottomOpen && (
        <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          {bottomTab === 'graph' && <KnowledgeGraph />}
          {bottomTab === 'timeline' && <MemoryTimeline />}
          {bottomTab === 'health' && <HealthPanel />}
        </div>
      )}
    </div>
  )
}
