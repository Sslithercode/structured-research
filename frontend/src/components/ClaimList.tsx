import { useState, useRef, useEffect, useMemo } from 'react'
import type { Claim, Source } from '../types'
import ClaimEditor from './ClaimEditor'

const CLAIM_TYPE_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  fact:           { bg: 'var(--bg-3)',         color: 'var(--ink-3)',    border: 'var(--border-2)' },
  prediction:     { bg: 'rgba(90,120,200,0.1)', color: '#6a8ee0',        border: 'rgba(90,120,200,0.25)' },
  opinion:        { bg: 'var(--accent-2)',      color: 'var(--accent)',   border: 'rgba(200,146,42,0.2)' },
  reported_speech:{ bg: 'rgba(61,140,94,0.08)', color: 'var(--high)',    border: 'rgba(61,140,94,0.2)' },
}

function highlightClaimInChunk(chunkText: string, claimText: string): React.ReactNode {
  const idx = chunkText.toLowerCase().indexOf(claimText.toLowerCase().slice(0, 40))
  if (idx === -1) return <span>{chunkText}</span>
  const end = idx + claimText.length
  return (
    <>
      {chunkText.slice(0, idx)}
      <mark style={{ background: 'rgba(200,146,42,0.25)', color: 'inherit', borderRadius: 2 }}>
        {chunkText.slice(idx, end)}
      </mark>
      {chunkText.slice(end)}
    </>
  )
}

interface Props {
  claims: Claim[]
  sources: Source[]
  onEdit?: (claimId: string, text: string) => void
  onDelete?: (claimId: string) => void
  onAdd?: (claim: Claim) => void
  deletedIds?: string[]
  editedTexts?: Record<string, string>
  showAdd?: boolean
  highlightClaimId?: string | null
}

function MatchBar({ score }: { score: number }) {
  const color = score > 0.75 ? 'var(--high)' : score > 0.45 ? 'var(--med)' : 'var(--low)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        height: 3, width: 60, background: 'var(--border)',
        borderRadius: 2, overflow: 'hidden',
      }}>
        <div style={{ height: '100%', width: `${score * 100}%`, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color }}>
        {(score * 100).toFixed(0)}%
      </span>
    </div>
  )
}

function ClaimCard({
  claim, sources, onEdit, onDelete, isDeleted, editedText, isHighlighted,
}: {
  claim: Claim
  sources: Source[]
  onEdit?: (claimId: string, text: string) => void
  onDelete?: (claimId: string) => void
  isDeleted: boolean
  editedText?: string
  isHighlighted?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [showProvenance, setShowProvenance] = useState(false)
  const [showOriginals, setShowOriginals] = useState(false)
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isHighlighted && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [isHighlighted])
  const source = sources.find(s => s.source_id === claim.source_id)
  const displayText = editedText ?? claim.text
  const hostname = source ? (() => { try { return new URL(source.url).hostname } catch { return source.url } })() : claim.source_id

  if (isDeleted) return null

  return (
    <>
      <div ref={cardRef} style={{
        padding: '12px 14px',
        border: `1px solid ${isHighlighted ? 'var(--accent)' : 'var(--border-2)'}`,
        marginBottom: 6,
        background: isHighlighted ? 'var(--accent-2)' : 'var(--bg)',
        opacity: isDeleted ? 0.4 : 1,
        position: 'relative',
        transition: 'background 0.2s, border-color 0.2s',
      }}>
        {/* origin badge */}
        {claim._origin === 'user' && (
          <div style={{
            position: 'absolute', top: 8, right: 8,
            fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--accent)',
            background: 'var(--accent-2)', padding: '1px 5px',
            border: '1px solid rgba(200,146,42,0.2)',
          }}>
            user
          </div>
        )}

        {/* metadata row */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color: 'var(--ink-3)', background: 'var(--bg-3)',
            padding: '1px 5px', border: '1px solid var(--border-2)',
          }}>
            {claim.claim_id}
          </span>

          {source && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent)', textDecoration: 'none' }}
            >
              {hostname}
            </a>
          )}

          {source && (
            <span className={`tier-badge tier-${source.reliability_tier}`}>
              {source.reliability_tier}
            </span>
          )}

          {claim.corroborated_by.length > 0 && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--high)', background: 'var(--high-bg)',
              padding: '1px 5px', border: '1px solid rgba(61,140,94,0.2)',
            }}>
              +{claim.corroborated_by.length} corroboration{claim.corroborated_by.length > 1 ? 's' : ''}
            </span>
          )}

          {claim.conflicts_with.length > 0 && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--conflict)', background: 'var(--conflict-bg)',
              padding: '1px 5px', border: '1px solid rgba(158,58,58,0.2)',
            }}>
              {claim.conflicts_with.length} conflict{claim.conflicts_with.length > 1 ? 's' : ''}
            </span>
          )}

          {(() => {
            const style = CLAIM_TYPE_COLORS[claim.claim_type] ?? CLAIM_TYPE_COLORS.fact
            return (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: style.color, background: style.bg,
                padding: '1px 5px', border: `1px solid ${style.border}`,
              }}>
                {claim.claim_type.replace('_', ' ')}
              </span>
            )
          })()}
        </div>

        {/* claim text */}
        <div className="claim-text" style={{ marginBottom: 10 }}>
          {editedText ? (
            <span style={{ borderBottom: '1px dashed var(--accent)' }}>{displayText}</span>
          ) : displayText}
        </div>

        {/* original phrasings before canonical rewrite */}
        {showOriginals && claim.original_texts && (
          <div style={{
            margin: '8px 0 10px',
            padding: '10px 12px',
            background: 'var(--bg-2)',
            border: '1px solid var(--border)',
            fontSize: 11, lineHeight: 1.6,
            color: 'var(--ink-2)',
            fontFamily: 'var(--font-mono)',
          }}>
            <div style={{ fontSize: 9, color: 'var(--ink-3)', marginBottom: 6, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              Original phrasings
            </div>
            {Object.entries(claim.original_texts).map(([srcId, text]) => {
              const src = sources.find(s => s.source_id === srcId)
              const label = src ? (() => { try { return new URL(src.url).hostname } catch { return srcId } })() : srcId
              return (
                <div key={srcId} style={{ marginBottom: 6 }}>
                  <span style={{ color: 'var(--accent)', fontSize: 9 }}>{label}: </span>
                  {text}
                </div>
              )
            })}
          </div>
        )}

        {/* provenance trace */}
        {showProvenance && claim.chunk_text && (
          <div style={{
            margin: '8px 0 10px',
            padding: '10px 12px',
            background: 'var(--bg-2)',
            border: '1px solid var(--border)',
            fontSize: 11, lineHeight: 1.6,
            color: 'var(--ink-2)',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'pre-wrap',
          }}>
            <div style={{ fontSize: 9, color: 'var(--ink-3)', marginBottom: 6, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              Source chunk
            </div>
            {highlightClaimInChunk(claim.chunk_text, claim.text)}
          </div>
        )}

        {/* bottom row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {claim.embedding_match != null && <MatchBar score={claim.embedding_match} />}
          <div style={{ flex: 1 }} />
          {claim.original_texts && Object.keys(claim.original_texts).length > 0 && (
            <button className="ghost" style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => setShowOriginals(v => !v)}>
              {showOriginals ? 'Hide originals' : 'Originals'}
            </button>
          )}
          {claim.chunk_text && (
            <button className="ghost" style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => setShowProvenance(v => !v)}>
              {showProvenance ? 'Hide source' : 'Source'}
            </button>
          )}
          {onEdit && (
            <button className="ghost" style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
          {onDelete && (
            <button className="danger" style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => onDelete(claim.claim_id)}>
              Delete
            </button>
          )}
        </div>
      </div>

      {editing && onEdit && (
        <ClaimEditor
          sources={sources}
          initial={claim}
          onSave={(updated) => { onEdit(claim.claim_id, updated.text); setEditing(false) }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  )
}

const CLAIM_TYPES = ['fact', 'prediction', 'opinion', 'reported_speech'] as const
const TIERS = ['high', 'medium', 'low'] as const

export default function ClaimList({
  claims, sources, onEdit, onDelete, onAdd,
  deletedIds = [], editedTexts = {}, showAdd = false, highlightClaimId,
}: Props) {
  const [addOpen, setAddOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set())
  const [tierFilter, setTierFilter] = useState<Set<string>>(new Set())
  const [onlyConflicts, setOnlyConflicts] = useState(false)
  const [onlyCorroborated, setOnlyCorroborated] = useState(false)

  const sourceMap = useMemo(() => Object.fromEntries(sources.map(s => [s.source_id, s])), [sources])

  const active = useMemo(() => {
    return claims.filter(c => {
      if (deletedIds.includes(c.claim_id)) return false
      if (search && !c.text.toLowerCase().includes(search.toLowerCase())) return false
      if (typeFilter.size > 0 && !typeFilter.has(c.claim_type)) return false
      if (tierFilter.size > 0) {
        const tier = sourceMap[c.source_id]?.reliability_tier
        if (!tier || !tierFilter.has(tier)) return false
      }
      if (onlyConflicts && c.conflicts_with.length === 0) return false
      if (onlyCorroborated && c.corroborated_by.length === 0) return false
      return true
    })
  }, [claims, deletedIds, search, typeFilter, tierFilter, onlyConflicts, onlyCorroborated, sourceMap])

  function toggleSet(set: Set<string>, val: string): Set<string> {
    const next = new Set(set)
    next.has(val) ? next.delete(val) : next.add(val)
    return next
  }

  const hasFilters = search || typeFilter.size > 0 || tierFilter.size > 0 || onlyConflicts || onlyCorroborated

  return (
    <div>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          {active.length}{hasFilters ? `/${claims.filter(c => !deletedIds.includes(c.claim_id)).length}` : ''} claims
        </span>
        <div style={{ flex: 1 }} />
        {showAdd && onAdd && (
          <button className="primary" style={{ fontSize: 10, padding: '4px 10px' }}
            onClick={() => setAddOpen(true)}>
            + Add Claim
          </button>
        )}
      </div>

      {/* filter bar */}
      <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <input
          type="text"
          placeholder="Search claims…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            width: '100%', boxSizing: 'border-box',
            padding: '5px 9px', fontSize: 11,
            background: 'var(--bg-2)', border: '1px solid var(--border-2)',
            color: 'var(--ink)', outline: 'none', fontFamily: 'var(--font-body)',
          }}
        />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {CLAIM_TYPES.map(t => (
            <button key={t} className="ghost"
              onClick={() => setTypeFilter(s => toggleSet(s, t))}
              style={{
                fontSize: 9, padding: '2px 7px',
                background: typeFilter.has(t) ? 'var(--accent-2)' : undefined,
                color: typeFilter.has(t) ? 'var(--accent)' : 'var(--ink-3)',
                border: `1px solid ${typeFilter.has(t) ? 'rgba(200,146,42,0.3)' : 'var(--border-2)'}`,
              }}>
              {t.replace('_', ' ')}
            </button>
          ))}
          <div style={{ width: 1, background: 'var(--border-2)', margin: '0 2px' }} />
          {TIERS.map(t => (
            <button key={t} className="ghost"
              onClick={() => setTierFilter(s => toggleSet(s, t))}
              style={{
                fontSize: 9, padding: '2px 7px',
                background: tierFilter.has(t) ? 'var(--bg-3)' : undefined,
                color: tierFilter.has(t) ? 'var(--ink)' : 'var(--ink-3)',
                border: `1px solid ${tierFilter.has(t) ? 'var(--border)' : 'var(--border-2)'}`,
              }}>
              {t}
            </button>
          ))}
          <div style={{ width: 1, background: 'var(--border-2)', margin: '0 2px' }} />
          <button className="ghost"
            onClick={() => setOnlyConflicts(v => !v)}
            style={{
              fontSize: 9, padding: '2px 7px',
              background: onlyConflicts ? 'var(--conflict-bg)' : undefined,
              color: onlyConflicts ? 'var(--conflict)' : 'var(--ink-3)',
              border: `1px solid ${onlyConflicts ? 'rgba(158,58,58,0.25)' : 'var(--border-2)'}`,
            }}>
            conflicts
          </button>
          <button className="ghost"
            onClick={() => setOnlyCorroborated(v => !v)}
            style={{
              fontSize: 9, padding: '2px 7px',
              background: onlyCorroborated ? 'var(--high-bg)' : undefined,
              color: onlyCorroborated ? 'var(--high)' : 'var(--ink-3)',
              border: `1px solid ${onlyCorroborated ? 'rgba(61,140,94,0.25)' : 'var(--border-2)'}`,
            }}>
            corroborated
          </button>
          {hasFilters && (
            <button className="ghost"
              onClick={() => { setSearch(''); setTypeFilter(new Set()); setTierFilter(new Set()); setOnlyConflicts(false); setOnlyCorroborated(false) }}
              style={{ fontSize: 9, padding: '2px 7px', color: 'var(--ink-3)' }}>
              clear
            </button>
          )}
        </div>
      </div>

      {active.length === 0 && (
        <div style={{ color: 'var(--ink-3)', fontSize: 12, padding: '12px 0' }}>
          {hasFilters ? 'No claims match filters.' : 'No claims.'}
        </div>
      )}

      {active.map(claim => (
        <ClaimCard
          key={claim.claim_id}
          claim={claim}
          sources={sources}
          onEdit={onEdit}
          onDelete={onDelete}
          isDeleted={deletedIds.includes(claim.claim_id)}
          editedText={editedTexts[claim.claim_id]}
          isHighlighted={highlightClaimId === claim.claim_id}
        />
      ))}

      {addOpen && onAdd && (
        <ClaimEditor
          sources={sources}
          onSave={(claim) => { onAdd(claim); setAddOpen(false) }}
          onClose={() => setAddOpen(false)}
        />
      )}
    </div>
  )
}
