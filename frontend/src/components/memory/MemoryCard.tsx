import React, { useState } from 'react'
import { useUIStore } from '../../store'

interface Memory {
  cube_id?: string
  id?: string
  type?: string
  memory_type?: string
  tier?: string
  content?: string
  tags?: string[]
  access_count?: number
  version?: number
  relevance_score?: number
  created_at?: string
  updated_at?: string
  session_id?: string
  provenance?: Record<string, unknown>
  extra?: { label?: string; detail?: string; key?: string }
}

function typeColor(type: string) {
  if (type === 'episodic') return 'var(--accent-purple)'
  if (type === 'semantic') return 'var(--accent-teal)'
  return 'var(--accent-orange)'
}

function tierColor(tier: string) {
  if (tier === 'hot') return 'var(--tier-hot)'
  if (tier === 'warm') return 'var(--tier-warm)'
  return 'var(--tier-cold)'
}

function timeAgo(iso?: string) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  return `${Math.round(diff / 3600)}h ago`
}

export function MemoryCard({ memory, isNew }: { memory: Memory; isNew?: boolean }) {
  const { flashedMemoryIds } = useUIStore()
  const [expanded, setExpanded] = useState(false)

  const id = memory.cube_id ?? memory.id ?? ''
  const type = (memory.type ?? memory.memory_type ?? 'episodic').toLowerCase()
  const tier = (memory.tier ?? 'cold').toLowerCase()
  const content = memory.content ?? ''
  const extra = memory.extra ?? {}
  const headline =
    typeof extra.label === 'string' && extra.label.trim() && extra.label.trim() !== content.trim().split('\n')[0]
      ? extra.label.trim()
      : null
  const tags: string[] = memory.tags ?? []
  const score = memory.relevance_score ?? 0
  const tc = typeColor(type)
  const tierC = tierColor(tier)
  const isFlashed = flashedMemoryIds.includes(id)
  const isHot = tier === 'hot'

  const typeLabel = type === 'kg_node' ? 'KG_NODE' : type.toUpperCase()
  const tierLabel = tier.toUpperCase()

  return (
    <div
      style={{
        borderLeft: `3px solid ${tc}`,
        background: 'var(--bg-surface)',
        borderRadius: 4,
        margin: '6px 8px',
        padding: '10px 12px',
        cursor: 'pointer',
        position: 'relative',
        animation: isNew
          ? 'memory-birth 0.4s cubic-bezier(0.34,1.56,0.64,1)'
          : isFlashed
          ? 'flash-danger 0.3s ease-out 4 alternate'
          : undefined,
        transition: 'background 0.15s',
        ...(isHot ? { animationName: isNew ? 'memory-birth, tier-hot-pulse' : 'tier-hot-pulse', animationDuration: isNew ? '0.4s, 2s' : '2s', animationIterationCount: isNew ? '1, infinite' : 'infinite' } : {}),
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-surface-3)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--bg-surface)' }}
      onClick={() => setExpanded((v) => !v)}
    >
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {/* Type badge */}
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: tc,
            background: `${tc}22`,
            border: `1px solid ${tc}66`,
            borderRadius: 3,
            padding: '1px 6px',
          }}>{typeLabel}</span>

          {/* Tier badge */}
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: tierC,
            background: `${tierC}1f`,
            border: `1px solid ${tierC}44`,
            borderRadius: 3,
            padding: '1px 6px',
            ...(isHot ? { animation: 'tier-hot-pulse 2s infinite' } : {}),
          }}>{tierLabel} ⬡</span>

          {isFlashed && (
            <span style={{ color: 'var(--accent-red)', fontSize: 11 }}>⚠</span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
            {timeAgo(memory.created_at)}
          </span>
          <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>{expanded ? '▾' : '▶'}</span>
        </div>
      </div>

      {headline && (
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: 6,
            letterSpacing: '0.02em',
          }}
        >
          {headline}
        </div>
      )}

      {/* Content */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-secondary)',
        lineHeight: 1.5,
        display: '-webkit-box',
        WebkitLineClamp: expanded ? 'unset' : 3,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
        marginBottom: 8,
      }}>
        {typeof extra.detail === 'string' && extra.detail && type === 'kg_node'
          ? extra.detail
          : content}
      </div>

      {/* Tags */}
      {tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
          {tags.map((tag) => (
            <span key={tag} style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--text-dim)',
              background: 'var(--bg-surface-3)',
              borderRadius: 3,
              padding: '1px 6px',
            }}>{tag}</span>
          ))}
        </div>
      )}

      {/* Meta row */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--text-dim)',
        display: 'flex',
        gap: 10,
        marginBottom: 8,
      }}>
        <span>ID: {id.slice(0, 6)}</span>
        <span>Access: {memory.access_count ?? 0}</span>
        <span>v{memory.version ?? 1}</span>
      </div>

      {/* Score bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>relevance score</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>{score.toFixed(2)}</span>
        </div>
        <div style={{ height: 4, background: 'var(--bg-surface-3)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${score * 100}%`,
            background: tc,
            borderRadius: 2,
            transition: 'width 0.3s ease',
          }} />
        </div>
      </div>

      {/* Provenance drawer */}
      {expanded && (
        <div style={{
          marginTop: 10,
          padding: '8px 10px',
          background: 'var(--bg-void)',
          borderTop: '1px dashed var(--border-dim)',
          borderRadius: 2,
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-dim)', marginBottom: 6 }}>
            PROVENANCE CHAIN ─────────────────────────
          </div>
          <div><span style={{ color: 'var(--text-dim)' }}>origin:</span>    {String((memory.provenance as any)?.origin ?? 'agent_inference')}</div>
          <div><span style={{ color: 'var(--text-dim)' }}>session:</span>   {memory.session_id ?? 'unknown'}</div>
          <div><span style={{ color: 'var(--text-dim)' }}>version:</span>   {memory.version ?? 1}</div>
          <div><span style={{ color: 'var(--text-dim)' }}>created:</span>   {memory.created_at ?? 'unknown'}</div>
          <div><span style={{ color: 'var(--text-dim)' }}>updated:</span>   {memory.updated_at ?? 'unknown'}</div>
          <div><span style={{ color: 'var(--text-dim)' }}>parent:</span>    {(memory.version ?? 1) === 1 ? 'none (v1)' : `v${(memory.version ?? 1) - 1}`}</div>
        </div>
      )}
    </div>
  )
}
