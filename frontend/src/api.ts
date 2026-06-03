import type { ClaimGraph, PipelineEvent } from './types'

const BASE = '/api'

export async function startResearchStream(
  query: string,
  onEvent: (event: PipelineEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/research/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch { /* ignore malformed */ }
      }
    }
  }
}

export async function combineGraphs(graphs: ClaimGraph[]): Promise<ClaimGraph> {
  const res = await fetch(`${BASE}/combine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graphs }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function approveStage(requestId: string, stage: string, approved: boolean) {
  await fetch(`${BASE}/approve-stage/${requestId}/${stage}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  })
}

export async function approveCombine(combineId: string, approved: boolean) {
  await fetch(`${BASE}/approve-combine/${combineId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  })
}

export async function fetchGraph(graphId: string): Promise<{ graph_id: string; query: string; graph: import('./types').ClaimGraph }> {
  const res = await fetch(`${BASE}/graphs/${graphId}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function subscribeToEvents(
  onEvent: (event: ServerEvent) => void,
): () => void {
  const es = new EventSource(`${BASE}/events`)
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  es.onerror = () => {
    // EventSource auto-reconnects — nothing to do
  }
  return () => es.close()
}

export async function deleteGraph(graphId: string): Promise<void> {
  const res = await fetch(`${BASE}/graphs/${graphId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export type ServerEvent =
  | { type: 'snapshot'; graphs: { graph_id: string; query: string; sources: number; claims: number }[] }
  | { type: 'graph_added'; graph_id: string; query: string; summary: object }
  | { type: 'graph_combined'; graph_id: string; query: string; source_ids: string[] }
  | { type: 'graph_deleted'; graph_id: string }
