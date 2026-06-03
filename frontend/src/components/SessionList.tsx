import { useStore } from '../store'

export default function SessionList() {
  const {
    sessions, selectedSessionId, selectSession,
    toggleSessionSelected, combineSelected, combineStatus,
    view, setView, combinedGraph, exportSession, exportCombined, removeSession,
  } = useStore()

  const selectedCount = sessions.filter(s => s.selected && s.graph).length
  const canCombine = selectedCount >= 2

  return (
    <aside style={{
      width: 260, flexShrink: 0,
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      background: 'var(--bg-2)',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '12px 16px 10px',
        borderBottom: '1px solid var(--border-2)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span className="section-label" style={{ flex: 1 }}>Sessions</span>
        <span className="mono">{sessions.length}</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {sessions.length === 0 && (
          <div style={{ padding: '24px 16px', color: 'var(--ink-3)', fontSize: 12, lineHeight: 1.6 }}>
            Run a search to start building your research graph.
          </div>
        )}
        {sessions.map(sess => (
          <div
            key={sess.id}
            onClick={() => { selectSession(sess.id); setView('session') }}
            style={{
              padding: '10px 16px',
              cursor: 'pointer',
              borderLeft: `2px solid ${selectedSessionId === sess.id && view === 'session' ? 'var(--accent)' : 'transparent'}`,
              background: selectedSessionId === sess.id && view === 'session' ? 'var(--bg-3)' : 'transparent',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { if (!(selectedSessionId === sess.id && view === 'session')) (e.currentTarget as HTMLElement).style.background = 'var(--bg-3)' }}
            onMouseLeave={e => { if (!(selectedSessionId === sess.id && view === 'session')) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <div
                className={`status-dot status-${sess.status}`}
                style={{ marginTop: 5 }}
                onClick={e => { e.stopPropagation(); if (sess.graph) toggleSessionSelected(sess.id) }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13, fontWeight: 500, color: 'var(--ink)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  marginBottom: 3,
                }}>
                  {sess.query}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {sess.graph && (
                    <>
                      <span className="mono">{sess.graph.sources.length} src</span>
                      <span className="mono">{sess.graph.claims.length} claims</span>
                    </>
                  )}
                  {sess.status === 'running' && <span className="mono" style={{ color: 'var(--accent)' }}>running…</span>}
                  {sess.status === 'waiting' && <span className="mono" style={{ color: '#6080c0' }}>waiting</span>}
                  {sess.status === 'error' && <span className="mono" style={{ color: 'var(--conflict)' }}>error</span>}
                </div>
              </div>
              {sess.graph && (
                <input
                  type="checkbox"
                  checked={sess.selected}
                  onChange={() => toggleSessionSelected(sess.id)}
                  onClick={e => e.stopPropagation()}
                  style={{ accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }}
                />
              )}
            </div>
            {selectedSessionId === sess.id && view === 'session' && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-2)', display: 'flex', gap: 6 }}>
                {sess.graph && (
                  <button className="ghost" style={{ fontSize: 10, padding: '3px 8px' }}
                    onClick={e => { e.stopPropagation(); exportSession(sess.id) }}>
                    Export JSON
                  </button>
                )}
                <button className="danger" style={{ fontSize: 10, padding: '3px 8px' }}
                  onClick={e => { e.stopPropagation(); removeSession(sess.id) }}>
                  Delete
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* combine */}
      <div style={{ borderTop: '1px solid var(--border)', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {combinedGraph && (
          <div
            onClick={() => setView('combined')}
            style={{
              padding: '8px 10px',
              border: `1px solid ${view === 'combined' ? 'var(--accent)' : 'var(--border)'}`,
              cursor: 'pointer', borderRadius: 'var(--radius)',
              background: view === 'combined' ? 'var(--accent-2)' : 'transparent',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 500,
                letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--accent)', background: 'var(--accent-2)',
                padding: '1px 5px', border: '1px solid rgba(200,146,42,0.2)',
              }}>
                Combined
              </span>
              <span className="mono">{combinedGraph.claims.length} claims</span>
            </div>
            <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>Unified graph</div>
            <button className="ghost" style={{ fontSize: 10, padding: '3px 8px', marginTop: 6 }}
              onClick={e => { e.stopPropagation(); exportCombined() }}>
              Export JSON
            </button>
          </div>
        )}

        <button
          className={canCombine ? 'primary' : ''}
          disabled={!canCombine || combineStatus === 'running'}
          onClick={combineSelected}
          style={{ width: '100%' }}
        >
          {combineStatus === 'running' ? 'Combining…' : `Combine (${selectedCount} selected)`}
        </button>

        {selectedCount > 0 && selectedCount < 2 && (
          <div style={{ fontSize: 11, color: 'var(--ink-3)', textAlign: 'center' }}>
            Select at least 2 sessions
          </div>
        )}
      </div>
    </aside>
  )
}
