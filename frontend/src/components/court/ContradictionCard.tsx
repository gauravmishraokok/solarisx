import React, { useState } from 'react'
import { resolveCourtItem } from '../../api/court'
import { ScoreBar } from './ScoreBar'
import { MergeModal } from './MergeModal'

interface SupportingEvidence {
  label: string
  content: string
}

interface QuarantineItem {
  id?: string
  quarantine_id?: string
  // Flat fields from backend
  incoming_content?: string
  conflicting_content?: string
  conflicting_cube_id?: string
  // Nested variants (legacy)
  incoming_memory?: { content?: string; cube_id?: string }
  conflicting_memory?: { content?: string; cube_id?: string }
  incoming?: { content?: string }
  conflicting?: { content?: string }
  // Score / reasoning
  contradiction_score?: number
  score?: number
  judge_reasoning?: string
  reasoning?: string
  // Suggested action
  suggested_resolution?: string
  suggested?: string
  // Supporting corroboration
  supporting_evidence?: SupportingEvidence[]
  // Timestamps
  created_at?: string
  timestamp?: string
}

interface Props {
  item: QuarantineItem
  onResolved: () => void
}

export function ContradictionCard({ item, onResolved }: Props) {
  const [resolving, setResolving] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [fading, setFading] = useState(false)

  const id = item.id ?? item.quarantine_id ?? ''
  const incomingContent =
    item.incoming_content ??
    item.incoming_memory?.content ??
    item.incoming?.content ??
    '—'
  const conflictContent =
    item.conflicting_content ??
    item.conflicting_memory?.content ??
    item.conflicting?.content ??
    '—'
  const score = item.contradiction_score ?? item.score ?? 0
  const reasoning = item.judge_reasoning ?? item.reasoning ?? '—'
  const suggested = (item.suggested_resolution ?? item.suggested ?? 'reject').toLowerCase()
  const evidence: SupportingEvidence[] = item.supporting_evidence ?? []
  const timestamp = item.created_at ?? item.timestamp ?? ''

  async function resolve(resolution: string, mergedContent?: string) {
    if (resolving) return
    setResolving(true)
    try {
      await resolveCourtItem(id, resolution, mergedContent)
    } catch {
      // optimistic UI — ignore errors
    }
    setFading(true)
    setTimeout(onResolved, 300)
  }

  // ── Button style helpers ──────────────────────────────────────────────────
  const btnBase: React.CSSProperties = {
    fontFamily: 'var(--font-display)',
    fontSize: 12,
    fontWeight: 600,
    padding: '7px 16px',
    borderRadius: 6,
    cursor: 'pointer',
    transition: 'background 0.15s, box-shadow 0.15s',
    display: 'flex',
    alignItems: 'center',
    gap: 5,
  }

  function btnStyle(
    color: string,
    glow: string,
    isSelected: boolean,
  ): React.CSSProperties {
    return {
      ...btnBase,
      border: `1px solid ${color}`,
      background: isSelected ? `${color}22` : 'transparent',
      color,
      boxShadow: isSelected ? `0 0 10px ${glow}` : undefined,
    }
  }

  return (
    <>
      {showMerge && (
        <MergeModal
          suggestedContent={`${incomingContent} [MERGED] ${conflictContent}`}
          onConfirm={(merged) => { setShowMerge(false); resolve('merge', merged) }}
          onCancel={() => setShowMerge(false)}
        />
      )}

      <div style={{
        margin: '8px 10px',
        border: '1px solid var(--border-base)',
        borderRadius: 6,
        background: 'var(--bg-surface-2)',
        overflow: 'hidden',
        opacity: fading ? 0 : 1,
        transition: 'opacity 0.3s ease',
      }}>
        {/* ── Header ────────────────────────────────────────────────────── */}
        <div style={{
          padding: '10px 14px',
          borderBottom: '1px solid var(--border-dim)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'rgba(245,166,35,0.04)',
        }}>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: 'var(--accent-amber)',
          }}>⚠ CONTRADICTION DETECTED</span>
          <div style={{ display: 'flex', gap: 10, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
            <span>#{id.slice(0, 8)}</span>
            <span>{timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
          </div>
        </div>

        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* ── Incoming memory ───────────────────────────────────────── */}
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent-cyan)', marginBottom: 6 }}>
              INCOMING CLAIM
            </div>
            <div style={{
              border: '1px solid rgba(0,210,255,0.35)',
              background: 'rgba(0,210,255,0.04)',
              borderRadius: 4,
              padding: '8px 10px',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              lineHeight: 1.5,
            }}>
              "{incomingContent}"
            </div>
          </div>

          {/* ── Conflicting memory ───────────────────────────────────── */}
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent-red)', marginBottom: 6 }}>
              CONFLICTS WITH ESTABLISHED MEMORY
            </div>
            <div style={{
              border: '1px solid rgba(255,71,87,0.4)',
              background: 'rgba(255,71,87,0.04)',
              borderRadius: 4,
              padding: '8px 10px',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              lineHeight: 1.5,
            }}>
              "{conflictContent}"
            </div>
          </div>

          {/* ── Supporting evidence (corroborating memories) ─────────── */}
          {evidence.length > 0 && (
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent-amber)', marginBottom: 6 }}>
                CORROBORATING EVIDENCE
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {evidence.map((ev, i) => (
                  <div key={i} style={{
                    border: '1px solid rgba(245,166,35,0.3)',
                    background: 'rgba(245,166,35,0.04)',
                    borderRadius: 4,
                    padding: '7px 10px',
                    display: 'flex',
                    gap: 8,
                    alignItems: 'flex-start',
                  }}>
                    <span style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: 9,
                      fontWeight: 700,
                      color: 'var(--accent-amber)',
                      whiteSpace: 'nowrap',
                      marginTop: 1,
                    }}>{ev.label.toUpperCase()}</span>
                    <span style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      lineHeight: 1.4,
                    }}>{ev.content}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Score bar ─────────────────────────────────────────────── */}
          <div style={{ paddingTop: 2, paddingBottom: 6 }}>
            <ScoreBar score={score} />
          </div>

          {/* ── Judge reasoning ───────────────────────────────────────── */}
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-dim)', marginBottom: 6 }}>
              JUDGE REASONING
            </div>
            <div style={{
              fontFamily: 'var(--font-body)',
              fontSize: 12,
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
              fontStyle: 'italic',
              borderLeft: '2px solid var(--border-dim)',
              paddingLeft: 10,
            }}>
              {reasoning}
            </div>
          </div>

          {/* ── Suggested action label ────────────────────────────────── */}
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--text-dim)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            COURT RECOMMENDATION:
            <span style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: 10,
              letterSpacing: '0.08em',
              color: suggested === 'accept' ? 'var(--accent-green)'
                : suggested === 'merge' ? 'var(--accent-amber)'
                : 'var(--accent-red)',
            }}>
              {suggested.toUpperCase()}
            </span>
          </div>

          {/* ── Action buttons (highlighted = court recommendation) ───── */}
          <div style={{ display: 'flex', gap: 8, paddingTop: 2 }}>
            <button
              onClick={() => resolve('accept')}
              disabled={resolving}
              style={btnStyle('var(--accent-green)', 'rgba(0,229,160,0.4)', suggested === 'accept')}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(0,229,160,0.18)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = suggested === 'accept' ? 'rgba(0,229,160,0.13)' : 'transparent')}
            >
              {suggested === 'accept' && <span style={{ fontSize: 10 }}>★</span>}
              ✓ Accept
            </button>

            <button
              onClick={() => resolve('reject')}
              disabled={resolving}
              style={btnStyle('var(--accent-red)', 'rgba(255,71,87,0.4)', suggested === 'reject')}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,71,87,0.18)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = suggested === 'reject' ? 'rgba(255,71,87,0.13)' : 'transparent')}
            >
              {suggested === 'reject' && <span style={{ fontSize: 10 }}>★</span>}
              ✗ Reject
            </button>

            <button
              onClick={() => setShowMerge(true)}
              disabled={resolving}
              style={btnStyle('var(--accent-amber)', 'rgba(245,166,35,0.4)', suggested === 'merge')}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(245,166,35,0.18)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = suggested === 'merge' ? 'rgba(245,166,35,0.13)' : 'transparent')}
            >
              {suggested === 'merge' && <span style={{ fontSize: 10 }}>★</span>}
              ⟳ Merge...
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
