import { useRef, useEffect } from 'react'
import { useStore } from './store'
import { startResearchStream, subscribeToEvents } from './api'
import SessionList from './components/SessionList'
import GraphWorkspace from './components/GraphWorkspace'
import ConfigPanel from './components/ConfigPanel'
import type { PipelineEvent } from './types'

export default function App() {
  const {
    addSession, pushEvent, setSessionGraph,
    setSessionRequestId, setSessionError, updateSessionStatus,
    showConfig, setShowConfig, ingestMcpGraph, ingestMcpSnapshot,
  } = useStore()
  const queryRef = useRef<HTMLInputElement>(null)

  // Subscribe to server-pushed events (MCP graphs, pipeline updates)
  useEffect(() => {
    const unsub = subscribeToEvents((event) => {
      if (event.type === 'snapshot') {
        ingestMcpSnapshot(event.graphs)
      } else if (event.type === 'graph_added') {
        ingestMcpGraph(event.graph_id, event.query)
      } else if (event.type === 'graph_combined') {
        ingestMcpGraph(event.graph_id, event.query)
      }
    })
    return unsub
  }, [])

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const query = queryRef.current?.value.trim()
    if (!query) return
    if (queryRef.current) queryRef.current.value = ''
    const id = `s-${Date.now()}`
    addSession(id, query)
    try {
      await startResearchStream(query, (event: PipelineEvent) => {
        pushEvent(id, event)
        if (event.stage === 'start' && event.request_id) setSessionRequestId(id, event.request_id)
        if (event.stage === 'waiting') updateSessionStatus(id, 'waiting')
        if (event.stage === 'result' && event.data) setSessionGraph(id, event.data.graph)
        if (event.stage === 'error') setSessionError(id, event.message ?? 'Unknown error')
      })
    } catch (err) {
      setSessionError(id, String(err))
    }
  }

  const importFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const json = JSON.parse(ev.target?.result as string)
        const graph = json.graph ?? json
        const query = json.query ?? file.name.replace('.json', '')
        useStore.getState().importGraph(graph, query)
      } catch { alert('Invalid JSON file') }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header style={{
        display: 'flex', alignItems: 'center', gap: 16,
        padding: '0 20px', height: 52,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-2)', flexShrink: 0,
      }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500,
          letterSpacing: '0.18em', color: 'var(--accent)', textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}>
          Research
        </span>

        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />

        <form onSubmit={handleSearch} style={{ flex: 1, display: 'flex', gap: 8, maxWidth: 620 }}>
          <input ref={queryRef} placeholder="Enter research query…" style={{ flex: 1, height: 32, padding: '0 12px' }} />
          <button type="submit" className="primary" style={{ height: 32, whiteSpace: 'nowrap' }}>Run Search</button>
        </form>

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', gap: 6 }}>
          <label style={{
            fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 600,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'var(--ink-2)', padding: '5px 12px',
            border: '1px solid var(--border)', borderRadius: 'var(--radius)',
            cursor: 'pointer',
          }}>
            Import
            <input type="file" accept=".json" onChange={importFile} style={{ display: 'none' }} />
          </label>
          <button className="ghost" onClick={() => setShowConfig(true)}>Config</button>
        </div>
      </header>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <SessionList />
        <GraphWorkspace />
      </div>

      {showConfig && <ConfigPanel onClose={() => setShowConfig(false)} />}
    </div>
  )
}
