import type { Claim, Source } from '../types'

interface Props {
  claims: Claim[]
  sources: Source[]
}

function ConflictPair({ claimA, claimB, sources }: {
  claimA: Claim
  claimB: Claim
  sources: Source[]
}) {
  const srcA = sources.find(s => s.source_id === claimA.source_id)
  const srcB = sources.find(s => s.source_id === claimB.source_id)
  const hostnameOf = (url?: string) => { try { return new URL(url ?? '').hostname } catch { return url ?? '' } }

  return (
    <div style={{
      border: '1px solid rgba(158,58,58,0.3)',
      marginBottom: 12,
      background: 'var(--bg)',
    }}>
      <div style={{
        padding: '7px 14px',
        background: 'var(--conflict-bg)',
        borderBottom: '1px solid rgba(158,58,58,0.2)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--conflict)',
          letterSpacing: '0.1em', textTransform: 'uppercase',
        }}>
          Conflict
        </span>
        <span className="mono">{claimA.claim_id}</span>
        <span style={{ color: 'var(--ink-3)' }}>vs</span>
        <span className="mono">{claimB.claim_id}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        {([
          [claimA, srcA],
          [claimB, srcB],
        ] as [Claim, Source | undefined][]).map(([claim, src], i) => (
          <div
            key={i}
            style={{
              padding: '12px 14px',
              borderRight: i === 0 ? '1px solid var(--border-2)' : undefined,
            }}
          >
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
              {src && (
                <>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent)', textDecoration: 'none' }}
                  >
                    {hostnameOf(src.url)}
                  </a>
                  <span className={`tier-badge tier-${src.reliability_tier}`}>{src.reliability_tier}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-3)' }}>
                    {src.reliability_score.toFixed(2)}
                  </span>
                </>
              )}
            </div>
            <div className="claim-text" style={{ fontSize: 15 }}>{claim.text}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ConflictPanel({ claims, sources }: Props) {
  // collect all unique conflict pairs from the claims list
  const seen = new Set<string>()
  const pairs: [Claim, Claim][] = []

  for (const claim of claims) {
    for (const otherId of claim.conflicts_with) {
      const key = [claim.claim_id, otherId].sort().join(':')
      if (seen.has(key)) continue
      seen.add(key)
      const other = claims.find(c => c.claim_id === otherId)
      if (other) pairs.push([claim, other])
    }
  }

  if (pairs.length === 0) {
    return (
      <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--ink-3)', fontSize: 12 }}>
        No conflicts detected.
      </div>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 12 }}>
        {pairs.length} conflict pair{pairs.length !== 1 ? 's' : ''} detected
      </div>
      {pairs.map(([a, b]) => (
        <ConflictPair key={`${a.claim_id}:${b.claim_id}`} claimA={a} claimB={b} sources={sources} />
      ))}
    </div>
  )
}
