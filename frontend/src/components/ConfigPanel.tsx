import { useState } from 'react'
import { useStore } from '../store'
import type { ReliabilityTier } from '../types'

interface TagInputProps {
  label: string
  values: string[]
  onChange: (vals: string[]) => void
  placeholder?: string
}

function TagInput({ label, values, onChange, placeholder }: TagInputProps) {
  const [draft, setDraft] = useState('')

  function add() {
    const v = draft.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setDraft('')
  }

  return (
    <div className="form-field">
      <label className="form-label">{label}</label>
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder={placeholder ?? 'Add entry…'}
          style={{ flex: 1, height: 30 }}
        />
        <button onClick={add} style={{ height: 30, flexShrink: 0 }}>Add</button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {values.map(v => (
          <span key={v} style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            background: 'var(--bg-3)', border: '1px solid var(--border)',
            padding: '2px 8px', display: 'flex', alignItems: 'center', gap: 6,
          }}>
            {v}
            <span
              style={{ cursor: 'pointer', color: 'var(--ink-3)', lineHeight: 1 }}
              onClick={() => onChange(values.filter(x => x !== v))}
            >×</span>
          </span>
        ))}
        {values.length === 0 && (
          <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>None</span>
        )}
      </div>
    </div>
  )
}

interface Props { onClose: () => void }

export default function ConfigPanel({ onClose }: Props) {
  const { config, setConfig } = useStore()
  const [local, setLocal] = useState({ ...config })

  function save() {
    setConfig(local)
    onClose()
  }

  const selectStyle = {
    background: 'var(--bg-2)', border: '1px solid var(--border)',
    color: 'var(--ink)', padding: '6px 8px',
    fontFamily: 'var(--font-ui)', fontSize: 12,
    borderRadius: 'var(--radius)', width: '100%',
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ width: 560 }} onClick={e => e.stopPropagation()}>
        <div className="modal-title">Configuration</div>

        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-3)',
          letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16,
        }}>
          Source Scoring
        </div>

        <TagInput
          label="Trusted Sources (domains, publications, author names)"
          values={local.trusted}
          onChange={v => setLocal(l => ({ ...l, trusted: v }))}
          placeholder="e.g. nature.com, Reuters, Dr. Jane Smith"
        />
        <TagInput
          label="Untrusted Sources (bias reliability score down)"
          values={local.untrusted}
          onChange={v => setLocal(l => ({ ...l, untrusted: v }))}
          placeholder="e.g. tabloidsite.com"
        />
        <TagInput
          label="Blocked Domains (never fetched)"
          values={local.blocked_domains}
          onChange={v => setLocal(l => ({ ...l, blocked_domains: v }))}
          placeholder="e.g. spamsite.com"
        />
        <TagInput
          label="Blocked Authors (skip documents by these authors)"
          values={local.blocked_authors}
          onChange={v => setLocal(l => ({ ...l, blocked_authors: v }))}
          placeholder="e.g. John Doe"
        />

        <div style={{
          height: 1, background: 'var(--border-2)', margin: '16px 0',
        }} />

        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-3)',
          letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16,
        }}>
          Pipeline Behavior
        </div>

        <div className="form-field">
          <label className="form-label">Min Reliability Tier</label>
          <select
            value={local.min_reliability_tier}
            onChange={e => setLocal(l => ({ ...l, min_reliability_tier: e.target.value as ReliabilityTier }))}
            style={selectStyle}
          >
            <option value="low">Low (include all)</option>
            <option value="medium">Medium (exclude low)</option>
            <option value="high">High (only high tier)</option>
          </select>
        </div>

        {(
          [
            ['require_corroboration', 'Require Corroboration (drop uncorroborated claims)'],
            ['interruptible', 'Interruptible Mode (pause pipeline at each stage for approval)'],
            ['require_combine_approval', 'Require Combine Approval (hold combine until UI approves)'],
          ] as [keyof typeof local, string][]
        ).map(([key, label]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <input
              type="checkbox"
              id={key}
              checked={local[key] as boolean}
              onChange={e => setLocal(l => ({ ...l, [key]: e.target.checked }))}
              style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
            />
            <label htmlFor={key} style={{ fontSize: 12, color: 'var(--ink-2)', cursor: 'pointer' }}>{label}</label>
          </div>
        ))}

        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" onClick={save}>Save Config</button>
        </div>
      </div>
    </div>
  )
}
