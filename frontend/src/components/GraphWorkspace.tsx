import { useStore, applyMutations } from '../store'
import type { GraphTab, ClaimGraph, Claim, Edge, ReliabilityTier } from '../types'
import PipelineLog from './PipelineLog'
import SourceList from './SourceList'
import ClaimList from './ClaimList'
import EdgeList from './EdgeList'
import ConflictPanel from './ConflictPanel'

const TABS: { key: GraphTab; label: string }[] = [
  { key: 'sources', label: 'Sources' },
  { key: 'claims', label: 'Claims' },
  { key: 'edges', label: 'Edges' },
  { key: 'conflicts', label: 'Conflicts' },
]

function TabBar({ active, onChange, graph }: {
  active: GraphTab
  onChange: (t: GraphTab) => void
  graph: ClaimGraph | null
}) {
  const conflictCount = graph?.claims.reduce((n, c) => n + (c.conflicts_with.length > 0 ? 1 : 0), 0) ?? 0
  const counts: Record<GraphTab, number | null> = {
    sources: graph?.sources.length ?? null,
    claims: graph?.claims.length ?? null,
    edges: graph?.edges.length ?? null,
    conflicts: conflictCount,
  }

  return (
    <div style={{
      display: 'flex', borderBottom: '1px solid var(--border)',
      background: 'var(--bg-2)', flexShrink: 0,
    }}>
      {TABS.map(({ key, label }) => (
        <button
          key={key}
          className="ghost"
          onClick={() => onChange(key)}
          style={{
            borderRadius: 0, border: 'none',
            borderBottom: `2px solid ${active === key ? 'var(--accent)' : 'transparent'}`,
            color: active === key ? 'var(--ink)' : 'var(--ink-3)',
            padding: '10px 16px', fontSize: 11,
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          {label}
          {counts[key] !== null && counts[key]! > 0 && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              background: key === 'conflicts' && conflictCount > 0 ? 'var(--conflict-bg)' : 'var(--bg-3)',
              color: key === 'conflicts' && conflictCount > 0 ? 'var(--conflict)' : 'var(--ink-3)',
              padding: '1px 5px', border: '1px solid var(--border-2)',
            }}>
              {counts[key]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 12, color: 'var(--ink-3)',
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 32, opacity: 0.15,
        letterSpacing: '0.05em',
      }}>
        [ ]
      </div>
      <div style={{ fontSize: 13 }}>Select a session or run a search</div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
        Use the query bar above to start building your research graph
      </div>
    </div>
  )
}

export default function GraphWorkspace() {
  const {
    sessions, selectedSessionId, view, combinedGraph,
    activeTab, setActiveTab, combinedMutations,
    editClaim, deleteClaim, addClaim, overrideReliability, deleteEdge, addEdge,
    editCombinedClaim, deleteCombinedClaim, addCombinedClaim,
    overrideCombinedReliability, deleteCombinedEdge, addCombinedEdge,
  } = useStore()


  const selectedSession = sessions.find(s => s.id === selectedSessionId)
  const isCombined = view === 'combined'

  // Resolve which graph + mutations to display
  let graph: ClaimGraph | null = null
  let title = ''
  let subtitle = ''
  let isBusy = false

  if (isCombined && combinedGraph) {
    graph = applyMutations(combinedGraph, combinedMutations)
    title = 'Combined Graph'
    subtitle = `${combinedGraph.sources.length} sources · ${combinedGraph.claims.length} claims`
  } else if (selectedSession) {
    graph = selectedSession.graph
      ? applyMutations(selectedSession.graph, selectedSession.mutations)
      : null
    title = selectedSession.query
    subtitle = selectedSession.graph
      ? `${selectedSession.graph.sources.length} sources · ${selectedSession.graph.claims.length} claims`
      : ''
    isBusy = selectedSession.status === 'running' || selectedSession.status === 'waiting'
  }

  if (!selectedSession && !isCombined) return (
    <main style={{ flex: 1, display: 'flex', overflow: 'hidden', background: 'var(--bg)' }}>
      <EmptyState />
    </main>
  )

  // Mutation bindings — point to either session or combined graph mutations
  const mutations = isCombined ? combinedMutations : selectedSession?.mutations
  const sessionId = selectedSession?.id ?? ''

  const handlers = isCombined ? {
    onEditClaim: (id: string, text: string) => editCombinedClaim(id, text),
    onDeleteClaim: (id: string) => deleteCombinedClaim(id),
    onAddClaim: (claim: Claim) => addCombinedClaim(claim),
    onOverrideReliability: (sid: string, score: number, tier: ReliabilityTier) =>
      overrideCombinedReliability(sid, score, tier),
    onDeleteEdge: (from: string, to: string) => deleteCombinedEdge(from, to),
    onAddEdge: (edge: Edge) => addCombinedEdge(edge),
  } : {
    onEditClaim: (id: string, text: string) => editClaim(sessionId, id, text),
    onDeleteClaim: (id: string) => deleteClaim(sessionId, id),
    onAddClaim: (claim: Claim) => addClaim(sessionId, claim),
    onOverrideReliability: (sid: string, score: number, tier: ReliabilityTier) =>
      overrideReliability(sessionId, sid, score, tier),
    onDeleteEdge: (from: string, to: string) => deleteEdge(sessionId, from, to),
    onAddEdge: (edge: Edge) => addEdge(sessionId, edge),
  }

  return (
    <main style={{ flex: 1, display: 'flex', overflow: 'hidden', background: 'var(--bg)' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* header */}
        <div style={{
          padding: '10px 16px', borderBottom: '1px solid var(--border)',
          background: 'var(--bg-2)', flexShrink: 0,
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          {isCombined && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent)',
              background: 'var(--accent-2)', padding: '1px 5px',
              border: '1px solid rgba(200,146,42,0.2)', letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}>Combined</span>
          )}
          {selectedSession && !isCombined && (
            <div className={`status-dot status-${selectedSession.status}`} />
          )}
          <h1 style={{
            fontFamily: 'var(--font-body)', fontSize: 16, fontWeight: 500,
            color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            margin: 0, flex: 1,
          }}>{title}</h1>
          {subtitle && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
              {subtitle}
            </div>
          )}
        </div>

        {/* pipeline log while running */}
        {selectedSession && !isCombined && isBusy && (
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--bg-2)' }}>
            <PipelineLog session={selectedSession} />
          </div>
        )}

        {/* collapsed pipeline log when done */}
        {selectedSession && !isCombined && selectedSession.status === 'done' && selectedSession.events.length > 0 && (
          <details style={{ borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
            <summary style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)',
              cursor: 'pointer', listStyle: 'none', padding: '6px 16px',
            }}>Pipeline log</summary>
            <div style={{ padding: '0 16px 12px' }}>
              <PipelineLog session={selectedSession} />
            </div>
          </details>
        )}

        <TabBar active={activeTab} onChange={setActiveTab} graph={graph} />

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
          {graph && activeTab === 'sources' && (
            <SourceList
              sources={graph.sources}
              onOverrideReliability={handlers.onOverrideReliability}
              reliabilityOverrides={mutations?.reliabilityOverrides}
            />
          )}
          {graph && activeTab === 'claims' && (
            <ClaimList
              claims={graph.claims}
              sources={graph.sources}
              onEdit={handlers.onEditClaim}
              onDelete={handlers.onDeleteClaim}
              onAdd={handlers.onAddClaim}
              deletedIds={mutations?.deletedClaimIds}
              editedTexts={mutations?.editedClaims}
              showAdd
            />
          )}
          {graph && activeTab === 'edges' && (
            <EdgeList
              edges={graph.edges}
              claims={graph.claims}
              onDelete={handlers.onDeleteEdge}
              onAdd={handlers.onAddEdge}
              deletedKeys={mutations?.deletedEdgeKeys}
            />
          )}
          {graph && activeTab === 'conflicts' && (
            <ConflictPanel claims={graph.claims} sources={graph.sources} />
          )}
          {!graph && (
            <div style={{ color: 'var(--ink-3)', fontSize: 12, paddingTop: 8 }}>
              {isBusy ? 'Running…' : 'No data yet.'}
            </div>
          )}
        </div>

      </div>
    </main>
  )
}
