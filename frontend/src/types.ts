export type ReliabilityTier = 'high' | 'medium' | 'low'

export interface Source {
  source_id: string
  url: string
  publication?: string | null
  authors: string[]
  date?: string | null
  reliability_score: number
  reliability_tier: ReliabilityTier
  reliability_reasoning?: Record<string, unknown> | null
}

export interface Claim {
  claim_id: string
  text: string
  source_id: string
  chunk_text: string
  chunk_id: string
  corroborated_by: string[]
  original_texts?: Record<string, string>  // source_id → original text before canonical rewrite
  conflicts_with: string[]
  embedding_match?: number | null
  faithfulness_match?: boolean | null
  claim_type: string  // fact | prediction | opinion | reported_speech
  _origin?: 'pipeline' | 'user'
}

export interface Edge {
  from_claim: string
  to_claim: string
  type: 'supports' | 'contradicts' | 'qualifies'
}

export interface ClaimGraph {
  sources: Source[]
  claims: Claim[]
  edges: Edge[]
}

export interface PipelineEvent {
  stage: string
  message?: string
  request_id?: string
  pause_stage?: string
  sources?: Array<{
    id: string
    url: string
    reliability_tier?: string
    reliability_score?: number
    publication?: string
    authors?: string[]
    date?: string
  }>
  count?: number
  claim_count?: number
  conflict_count?: number
  data?: { query: string; graph: ClaimGraph; response: string; sentence_scores: unknown[] }
  claims?: Array<{ id: string; text: string; source_id: string; corroborated_by?: string[] }>
  conflicts?: Array<{ a: string; b: string }>
}

export type SessionStatus = 'running' | 'waiting' | 'done' | 'error'

export interface SessionMutations {
  editedClaims: Record<string, string>
  deletedClaimIds: string[]
  addedClaims: Claim[]
  reliabilityOverrides: Record<string, { score: number; tier: ReliabilityTier }>
  deletedEdgeKeys: string[]
  addedEdges: Edge[]
}

export interface Session {
  id: string
  query: string
  status: SessionStatus
  events: PipelineEvent[]
  graph: ClaimGraph | null
  requestId: string | null
  error?: string
  selected: boolean
  mutations: SessionMutations
}

export interface AppConfig {
  trusted: string[]
  untrusted: string[]
  blocked_domains: string[]
  blocked_authors: string[]
  require_combine_approval: boolean
  interruptible: boolean
  require_corroboration: boolean
  min_reliability_tier: ReliabilityTier
}

export type WorkspaceView = 'session' | 'combined'
export type GraphTab = 'sources' | 'claims' | 'edges' | 'conflicts'
