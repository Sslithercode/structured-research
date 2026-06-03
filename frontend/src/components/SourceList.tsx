import { useState } from 'react'
import type { Source, ReliabilityTier } from '../types'

interface Props {
  sources: Source[]
  onOverrideReliability?: (sourceId: string, score: number, tier: ReliabilityTier) => void
  reliabilityOverrides?: Record<string, { score: number; tier: ReliabilityTier }>
}

const TIER_OPTIONS: ReliabilityTier[] = ['high', 'medium', 'low']

function SourceCard({
  source, onOverride, override,
}: {
  source: Source
  onOverride?: (sourceId: string, score: number, tier: ReliabilityTier) => void
  override?: { score: number; tier: ReliabilityTier }
}) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editScore, setEditScore] = useState(String(source.reliability_score.toFixed(2)))
  const [editTier, setEditTier] = useState<ReliabilityTier>(source.reliability_tier)

  const tier = override?.tier ?? source.reliability_tier
  const score = override?.score ?? source.reliability_score

  const hostname = (() => { try { return new URL(source.url).hostname } catch { return source.url } })()

  function saveOverride() {
    const s = Math.max(0, Math.min(1, parseFloat(editScore) || 0))
    onOverride?.(source.source_id, s, editTier)
    setEditing(false)
  }

  return (
    <div style={{
      border: '1px solid var(--border-2)',
      marginBottom: 8,
      background: 'var(--bg)',
    }}>
      <div
        style={{ padding: '10px 14px', cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'flex-start' }}
        onClick={() => setExpanded(v => !v)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
            <span className={`tier-badge tier-${tier}`}>{tier}</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: tier === 'high' ? 'var(--high)' : tier === 'low' ? 'var(--low)' : 'var(--med)',
            }}>
              {score.toFixed(2)}
            </span>
            {override && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent)',
                background: 'var(--accent-2)', padding: '1px 5px',
                border: '1px solid rgba(200,146,42,0.2)',
              }}>
                override
              </span>
            )}
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--accent)', textDecoration: 'none',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240,
              }}
            >
              {hostname}
            </a>
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginBottom: 2 }}>
            {source.publication || hostname}
          </div>
          {(source.authors.length > 0 || source.date) && (
            <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              {source.authors.slice(0, 3).join(', ')}{source.authors.length > 3 ? ` +${source.authors.length - 3}` : ''}
              {source.authors.length > 0 && source.date && ' · '}
              {source.date}
            </div>
          )}
        </div>
        <span style={{ color: 'var(--ink-3)', fontSize: 12, flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div style={{
          padding: '10px 14px', borderTop: '1px solid var(--border-2)',
          background: 'var(--bg-2)',
        }}>
          <div style={{ marginBottom: 10 }}>
            <div className="section-label" style={{ marginBottom: 6 }}>Full URL</div>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent)',
                wordBreak: 'break-all', textDecoration: 'none',
              }}
            >
              {source.url}
            </a>
          </div>

          {source.reliability_reasoning && Object.keys(source.reliability_reasoning).length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div className="section-label" style={{ marginBottom: 6 }}>Reliability Breakdown</div>
              {Object.entries(source.reliability_reasoning)
                .filter(([k]) => !['tier', 'reliability'].includes(k))
                .map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', gap: 8, marginBottom: 2 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)', minWidth: 140 }}>{k}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-2)' }}>{String(v)}</span>
                  </div>
                ))}
            </div>
          )}

          {onOverride && !editing && (
            <button className="ghost" style={{ fontSize: 10 }} onClick={() => setEditing(true)}>
              Override Reliability
            </button>
          )}

          {editing && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="number" min="0" max="1" step="0.01"
                value={editScore}
                onChange={e => setEditScore(e.target.value)}
                style={{ width: 70, height: 28, padding: '0 8px' }}
              />
              <select
                value={editTier}
                onChange={e => setEditTier(e.target.value as ReliabilityTier)}
                style={{
                  background: 'var(--bg-2)', border: '1px solid var(--border)',
                  color: 'var(--ink)', padding: '4px 8px', fontFamily: 'var(--font-ui)',
                  fontSize: 11, height: 28,
                }}
              >
                {TIER_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <button className="primary" style={{ height: 28 }} onClick={saveOverride}>Save</button>
              <button className="ghost" style={{ height: 28 }} onClick={() => setEditing(false)}>Cancel</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function SourceList({ sources, onOverrideReliability, reliabilityOverrides = {} }: Props) {
  if (sources.length === 0) {
    return <div style={{ color: 'var(--ink-3)', padding: 16, fontSize: 12 }}>No sources yet.</div>
  }
  return (
    <div>
      {sources.map(s => (
        <SourceCard
          key={s.source_id}
          source={s}
          onOverride={onOverrideReliability}
          override={reliabilityOverrides[s.source_id]}
        />
      ))}
    </div>
  )
}
