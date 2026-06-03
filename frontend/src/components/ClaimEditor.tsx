import { useState } from 'react'
import type { Claim, Source } from '../types'

interface Props {
  sources: Source[]
  initial?: Partial<Claim>
  onSave: (claim: Claim) => void
  onClose: () => void
}

export default function ClaimEditor({ sources, initial, onSave, onClose }: Props) {
  const [text, setText] = useState(initial?.text ?? '')
  const [sourceId, setSourceId] = useState(initial?.source_id ?? sources[0]?.source_id ?? '')

  function handleSave() {
    if (!text.trim() || !sourceId) return
    const claim: Claim = {
      claim_id: initial?.claim_id ?? `user-${Date.now()}`,
      text: text.trim(),
      source_id: sourceId,
      chunk_text: initial?.chunk_text ?? text.trim(),
      chunk_id: initial?.chunk_id ?? 'user',
      corroborated_by: initial?.corroborated_by ?? [],
      conflicts_with: initial?.conflicts_with ?? [],
      _origin: 'user',
    }
    onSave(claim)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-title">{initial?.claim_id ? 'Edit Claim' : 'Add Claim'}</div>

        <div className="form-field">
          <label className="form-label">Claim Text</label>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="Enter an atomic fact…"
            style={{ fontFamily: 'var(--font-body)', fontSize: 16, minHeight: 100 }}
            autoFocus
          />
        </div>

        <div className="form-field">
          <label className="form-label">Source</label>
          <select
            value={sourceId}
            onChange={e => setSourceId(e.target.value)}
            style={{
              background: 'var(--bg-2)', border: '1px solid var(--border)',
              color: 'var(--ink)', padding: '7px 10px',
              fontFamily: 'var(--font-ui)', fontSize: 12,
              borderRadius: 'var(--radius)',
            }}
          >
            {sources.map(s => (
              <option key={s.source_id} value={s.source_id}>
                [{s.source_id}] {s.publication || (() => { try { return new URL(s.url).hostname } catch { return s.url } })()}
              </option>
            ))}
          </select>
        </div>

        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" onClick={handleSave} disabled={!text.trim()}>
            {initial?.claim_id ? 'Save' : 'Add Claim'}
          </button>
        </div>
      </div>
    </div>
  )
}
