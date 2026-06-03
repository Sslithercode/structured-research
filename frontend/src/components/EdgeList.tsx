import { useState } from 'react'
import type { Edge, Claim } from '../types'

interface Props {
  edges: Edge[]
  claims: Claim[]
  onDelete?: (fromClaim: string, toClaim: string) => void
  onAdd?: (edge: Edge) => void
  deletedKeys?: string[]
}

function EdgeRow({
  edge, claims, onDelete, isDeleted,
}: {
  edge: Edge
  claims: Claim[]
  onDelete?: (from: string, to: string) => void
  isDeleted: boolean
}) {
  if (isDeleted) return null
  const claimA = claims.find(c => c.claim_id === edge.from_claim)
  const claimB = claims.find(c => c.claim_id === edge.to_claim)

  return (
    <div style={{
      padding: '10px 14px', border: '1px solid var(--border-2)',
      marginBottom: 6, background: 'var(--bg)',
      borderLeft: `3px solid ${edge.type === 'contradicts' ? 'var(--conflict)' : edge.type === 'supports' ? 'var(--high)' : 'var(--accent)'}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span className={`edge-badge edge-${edge.type}`}>{edge.type}</span>
        <span className="mono">{edge.from_claim}</span>
        <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>→</span>
        <span className="mono">{edge.to_claim}</span>
        <div style={{ flex: 1 }} />
        {onDelete && (
          <button className="danger" style={{ fontSize: 10, padding: '2px 8px' }}
            onClick={() => onDelete(edge.from_claim, edge.to_claim)}>
            Remove
          </button>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div style={{
          padding: '8px 10px', background: 'var(--bg-2)',
          border: '1px solid var(--border-2)', fontSize: 12,
          fontFamily: 'var(--font-body)', lineHeight: 1.5, color: 'var(--ink-2)',
        }}>
          {claimA ? claimA.text : <span style={{ color: 'var(--ink-3)' }}>Claim not found</span>}
        </div>
        <div style={{
          padding: '8px 10px', background: 'var(--bg-2)',
          border: '1px solid var(--border-2)', fontSize: 12,
          fontFamily: 'var(--font-body)', lineHeight: 1.5, color: 'var(--ink-2)',
        }}>
          {claimB ? claimB.text : <span style={{ color: 'var(--ink-3)' }}>Claim not found</span>}
        </div>
      </div>
    </div>
  )
}

function AddEdgeForm({ claims, onAdd, onClose }: {
  claims: Claim[]
  onAdd: (edge: Edge) => void
  onClose: () => void
}) {
  const [fromId, setFromId] = useState(claims[0]?.claim_id ?? '')
  const [toId, setToId] = useState(claims[1]?.claim_id ?? '')
  const [type, setType] = useState<Edge['type']>('supports')

  const selectStyle = {
    background: 'var(--bg-2)', border: '1px solid var(--border)',
    color: 'var(--ink)', padding: '6px 8px',
    fontFamily: 'var(--font-ui)', fontSize: 11,
    borderRadius: 'var(--radius)', width: '100%',
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-title">Add Edge</div>
        <div className="form-field">
          <label className="form-label">From Claim</label>
          <select value={fromId} onChange={e => setFromId(e.target.value)} style={selectStyle}>
            {claims.map(c => (
              <option key={c.claim_id} value={c.claim_id}>
                [{c.claim_id}] {c.text.slice(0, 60)}…
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label className="form-label">Relationship</label>
          <select value={type} onChange={e => setType(e.target.value as Edge['type'])} style={selectStyle}>
            <option value="supports">supports</option>
            <option value="contradicts">contradicts</option>
            <option value="qualifies">qualifies</option>
          </select>
        </div>
        <div className="form-field">
          <label className="form-label">To Claim</label>
          <select value={toId} onChange={e => setToId(e.target.value)} style={selectStyle}>
            {claims.map(c => (
              <option key={c.claim_id} value={c.claim_id}>
                [{c.claim_id}] {c.text.slice(0, 60)}…
              </option>
            ))}
          </select>
        </div>
        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary"
            disabled={!fromId || !toId || fromId === toId}
            onClick={() => { onAdd({ from_claim: fromId, to_claim: toId, type }); onClose() }}>
            Add Edge
          </button>
        </div>
      </div>
    </div>
  )
}

export default function EdgeList({ edges, claims, onDelete, onAdd, deletedKeys = [] }: Props) {
  const [addOpen, setAddOpen] = useState(false)
  const active = edges.filter(e => !deletedKeys.includes(`${e.from_claim}:${e.to_claim}`))

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{active.length} edges</span>
        <div style={{ flex: 1 }} />
        {onAdd && (
          <button className="primary" style={{ fontSize: 10, padding: '4px 10px' }}
            onClick={() => setAddOpen(true)}>
            + Add Edge
          </button>
        )}
      </div>

      {active.length === 0 && (
        <div style={{ color: 'var(--ink-3)', fontSize: 12, padding: '12px 0' }}>No edges.</div>
      )}

      {edges.map((edge, i) => (
        <EdgeRow
          key={i}
          edge={edge}
          claims={claims}
          onDelete={onDelete}
          isDeleted={deletedKeys.includes(`${edge.from_claim}:${edge.to_claim}`)}
        />
      ))}

      {addOpen && onAdd && (
        <AddEdgeForm claims={claims} onAdd={onAdd} onClose={() => setAddOpen(false)} />
      )}
    </div>
  )
}
