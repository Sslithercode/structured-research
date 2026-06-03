import { create } from 'zustand'
import { combineGraphs, fetchGraph, deleteGraph } from './api'
import type {
  Session, ClaimGraph, Claim, Edge, AppConfig,
  SessionMutations, ReliabilityTier, GraphTab, WorkspaceView,
} from './types'

const DEFAULT_MUTATIONS = (): SessionMutations => ({
  editedClaims: {},
  deletedClaimIds: [],
  addedClaims: [],
  reliabilityOverrides: {},
  deletedEdgeKeys: [],
  addedEdges: [],
})

const DEFAULT_CONFIG: AppConfig = {
  trusted: [],
  untrusted: [],
  blocked_domains: [],
  blocked_authors: [],
  require_combine_approval: false,
  interruptible: false,
  require_corroboration: false,
  min_reliability_tier: 'low',
}

export function applyMutations(graph: ClaimGraph, mutations: SessionMutations): ClaimGraph {
  const deletedSet = new Set(mutations.deletedClaimIds)
  const deletedEdgeSet = new Set(mutations.deletedEdgeKeys)

  const claims = [
    ...graph.claims
      .filter(c => !deletedSet.has(c.claim_id))
      .map(c => mutations.editedClaims[c.claim_id]
        ? { ...c, text: mutations.editedClaims[c.claim_id] }
        : c),
    ...mutations.addedClaims,
  ]

  const sources = graph.sources.map(s => {
    const ov = mutations.reliabilityOverrides[s.source_id]
    return ov ? { ...s, reliability_score: ov.score, reliability_tier: ov.tier } : s
  })

  const survivingIds = new Set(claims.map(c => c.claim_id))
  const edges = [
    ...graph.edges.filter(e =>
      !deletedEdgeSet.has(`${e.from_claim}:${e.to_claim}`) &&
      survivingIds.has(e.from_claim) &&
      survivingIds.has(e.to_claim)
    ),
    ...mutations.addedEdges.filter(e =>
      survivingIds.has(e.from_claim) && survivingIds.has(e.to_claim)
    ),
  ]

  return { sources, claims, edges }
}

interface Store {
  sessions: Session[]
  selectedSessionId: string | null
  combinedGraph: ClaimGraph | null
  combinedMutations: SessionMutations
  view: WorkspaceView
  activeTab: GraphTab
  showConfig: boolean
  config: AppConfig
  combineStatus: 'idle' | 'running' | 'done' | 'error'
  combineError: string | null

  // session actions
  addSession: (id: string, query: string) => void
  updateSessionStatus: (id: string, status: Session['status']) => void
  pushEvent: (id: string, event: import('./types').PipelineEvent) => void
  setSessionGraph: (id: string, graph: ClaimGraph) => void
  setSessionRequestId: (id: string, requestId: string) => void
  setSessionError: (id: string, error: string) => void
  toggleSessionSelected: (id: string) => void
  selectSession: (id: string | null) => void

  // mutation actions on sessions
  editClaim: (sessionId: string, claimId: string, text: string) => void
  deleteClaim: (sessionId: string, claimId: string) => void
  addClaim: (sessionId: string, claim: Claim) => void
  overrideReliability: (sessionId: string, sourceId: string, score: number, tier: ReliabilityTier) => void
  deleteEdge: (sessionId: string, fromClaim: string, toClaim: string) => void
  addEdge: (sessionId: string, edge: Edge) => void

  // combined graph mutations
  editCombinedClaim: (claimId: string, text: string) => void
  deleteCombinedClaim: (claimId: string) => void
  addCombinedClaim: (claim: Claim) => void
  overrideCombinedReliability: (sourceId: string, score: number, tier: ReliabilityTier) => void
  deleteCombinedEdge: (fromClaim: string, toClaim: string) => void
  addCombinedEdge: (edge: Edge) => void

  // combine
  combineSelected: () => Promise<void>

  // view
  setView: (v: WorkspaceView) => void
  setActiveTab: (t: GraphTab) => void
  setShowConfig: (v: boolean) => void
  setConfig: (cfg: Partial<AppConfig>) => void

  // export/import
  exportSession: (sessionId: string) => void
  exportCombined: () => void
  importGraph: (graph: ClaimGraph, query?: string) => void

  // session deletion
  removeSession: (sessionId: string) => Promise<void>

  // MCP-driven graph ingestion
  ingestMcpGraph: (graphId: string, query: string) => Promise<void>
  ingestMcpSnapshot: (graphs: { graph_id: string; query: string }[]) => Promise<void>
}

export const useStore = create<Store>((set, get) => ({
  sessions: [],
  selectedSessionId: null,
  combinedGraph: null,
  combinedMutations: DEFAULT_MUTATIONS(),
  view: 'session',
  activeTab: 'sources',
  showConfig: false,
  config: DEFAULT_CONFIG,
  combineStatus: 'idle',
  combineError: null,

  addSession: (id, query) => set(s => ({
    sessions: [...s.sessions, {
      id, query, status: 'running', events: [], graph: null,
      requestId: null, selected: false, mutations: DEFAULT_MUTATIONS(),
    }],
    selectedSessionId: id,
    view: 'session',
  })),

  updateSessionStatus: (id, status) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === id ? { ...sess, status } : sess),
  })),

  pushEvent: (id, event) => set(s => ({
    sessions: s.sessions.map(sess =>
      sess.id === id ? { ...sess, events: [...sess.events, event] } : sess
    ),
  })),

  setSessionGraph: (id, graph) => set(s => ({
    sessions: s.sessions.map(sess =>
      sess.id === id ? { ...sess, graph, status: 'done' } : sess
    ),
  })),

  setSessionRequestId: (id, requestId) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === id ? { ...sess, requestId } : sess),
  })),

  setSessionError: (id, error) => set(s => ({
    sessions: s.sessions.map(sess =>
      sess.id === id ? { ...sess, error, status: 'error' } : sess
    ),
  })),

  toggleSessionSelected: (id) => set(s => ({
    sessions: s.sessions.map(sess =>
      sess.id === id ? { ...sess, selected: !sess.selected } : sess
    ),
  })),

  selectSession: (id) => set({ selectedSessionId: id, view: 'session' }),

  editClaim: (sessionId, claimId, text) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: { ...sess.mutations, editedClaims: { ...sess.mutations.editedClaims, [claimId]: text } },
    } : sess),
  })),

  deleteClaim: (sessionId, claimId) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: { ...sess.mutations, deletedClaimIds: [...sess.mutations.deletedClaimIds, claimId] },
    } : sess),
  })),

  addClaim: (sessionId, claim) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: { ...sess.mutations, addedClaims: [...sess.mutations.addedClaims, claim] },
    } : sess),
  })),

  overrideReliability: (sessionId, sourceId, score, tier) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: {
        ...sess.mutations,
        reliabilityOverrides: { ...sess.mutations.reliabilityOverrides, [sourceId]: { score, tier } },
      },
    } : sess),
  })),

  deleteEdge: (sessionId, fromClaim, toClaim) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: {
        ...sess.mutations,
        deletedEdgeKeys: [...sess.mutations.deletedEdgeKeys, `${fromClaim}:${toClaim}`],
      },
    } : sess),
  })),

  addEdge: (sessionId, edge) => set(s => ({
    sessions: s.sessions.map(sess => sess.id === sessionId ? {
      ...sess,
      mutations: { ...sess.mutations, addedEdges: [...sess.mutations.addedEdges, edge] },
    } : sess),
  })),

  editCombinedClaim: (claimId, text) => set(s => ({
    combinedMutations: { ...s.combinedMutations, editedClaims: { ...s.combinedMutations.editedClaims, [claimId]: text } },
  })),

  deleteCombinedClaim: (claimId) => set(s => ({
    combinedMutations: { ...s.combinedMutations, deletedClaimIds: [...s.combinedMutations.deletedClaimIds, claimId] },
  })),

  addCombinedClaim: (claim) => set(s => ({
    combinedMutations: { ...s.combinedMutations, addedClaims: [...s.combinedMutations.addedClaims, claim] },
  })),

  overrideCombinedReliability: (sourceId, score, tier) => set(s => ({
    combinedMutations: {
      ...s.combinedMutations,
      reliabilityOverrides: { ...s.combinedMutations.reliabilityOverrides, [sourceId]: { score, tier } },
    },
  })),

  deleteCombinedEdge: (fromClaim, toClaim) => set(s => ({
    combinedMutations: {
      ...s.combinedMutations,
      deletedEdgeKeys: [...s.combinedMutations.deletedEdgeKeys, `${fromClaim}:${toClaim}`],
    },
  })),

  addCombinedEdge: (edge) => set(s => ({
    combinedMutations: { ...s.combinedMutations, addedEdges: [...s.combinedMutations.addedEdges, edge] },
  })),

  combineSelected: async () => {
    const { sessions } = get()
    const selected = sessions.filter(s => s.selected && s.graph)
    if (selected.length < 2) return
    set({ combineStatus: 'running', combineError: null })
    try {
      const editedGraphs = selected.map(s => applyMutations(s.graph!, s.mutations))
      const unified = await combineGraphs(editedGraphs)
      set({ combinedGraph: unified, combinedMutations: DEFAULT_MUTATIONS(), combineStatus: 'done', view: 'combined', activeTab: 'claims' })
    } catch (e) {
      set({ combineStatus: 'error', combineError: String(e) })
    }
  },

  setView: (v) => set({ view: v }),
  setActiveTab: (t) => set({ activeTab: t }),
  setShowConfig: (v) => set({ showConfig: v }),
  setConfig: (cfg) => set(s => ({ config: { ...s.config, ...cfg } })),

  exportSession: (sessionId) => {
    const { sessions } = get()
    const sess = sessions.find(s => s.id === sessionId)
    if (!sess?.graph) return
    const graph = applyMutations(sess.graph, sess.mutations)
    const blob = new Blob([JSON.stringify({ query: sess.query, graph }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `research-${sess.query.slice(0, 30).replace(/\s+/g, '-')}.json`
    a.click()
    URL.revokeObjectURL(url)
  },

  exportCombined: () => {
    const { combinedGraph, combinedMutations } = get()
    if (!combinedGraph) return
    const graph = applyMutations(combinedGraph, combinedMutations)
    const blob = new Blob([JSON.stringify({ query: 'combined', graph }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `research-combined.json`
    a.click()
    URL.revokeObjectURL(url)
  },

  importGraph: (graph, query = 'imported') => {
    const id = `import-${Date.now()}`
    set(s => ({
      sessions: [...s.sessions, {
        id, query, status: 'done', events: [], graph,
        requestId: null, selected: false, mutations: DEFAULT_MUTATIONS(),
      }],
      selectedSessionId: id,
      view: 'session',
    }))
  },

  removeSession: async (sessionId) => {
    // If it's an MCP-backed session, delete from backend too
    if (sessionId.startsWith('mcp-')) {
      const graphId = sessionId.slice(4)
      try { await deleteGraph(graphId) } catch { /* best effort */ }
    }
    set(s => {
      const remaining = s.sessions.filter(sess => sess.id !== sessionId)
      const newSelected = s.selectedSessionId === sessionId
        ? (remaining[0]?.id ?? null)
        : s.selectedSessionId
      return { sessions: remaining, selectedSessionId: newSelected }
    })
  },

  ingestMcpGraph: async (graphId, query) => {
    // Don't add duplicates
    const existing = get().sessions.find(s => s.id === `mcp-${graphId}`)
    if (existing) return
    const id = `mcp-${graphId}`
    set(s => ({
      sessions: [...s.sessions, {
        id, query, status: 'running', events: [], graph: null,
        requestId: null, selected: false, mutations: DEFAULT_MUTATIONS(),
      }],
      selectedSessionId: id,
      view: 'session',
    }))
    try {
      const data = await fetchGraph(graphId)
      set(s => ({
        sessions: s.sessions.map(sess =>
          sess.id === id ? { ...sess, graph: data.graph, status: 'done' } : sess
        ),
      }))
    } catch (e) {
      set(s => ({
        sessions: s.sessions.map(sess =>
          sess.id === id ? { ...sess, status: 'error', error: String(e) } : sess
        ),
      }))
    }
  },

  ingestMcpSnapshot: async (graphs) => {
    const { sessions } = get()
    const existingIds = new Set(sessions.map(s => s.id))
    for (const { graph_id, query } of graphs) {
      if (!existingIds.has(`mcp-${graph_id}`)) {
        await get().ingestMcpGraph(graph_id, query)
      }
    }
  },
}))
