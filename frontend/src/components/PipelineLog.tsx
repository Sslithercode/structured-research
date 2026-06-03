import { useEffect, useRef } from 'react'
import { approveStage } from '../api'
import type { PipelineEvent, Session } from '../types'

const STAGE_LABELS: Record<string, string> = {
  start: 'INIT',
  fetch: 'FETCH',
  fetch_done: 'FETCH',
  extract: 'EXTRACT',
  extract_done: 'EXTRACT',
  merge: 'MERGE',
  merge_done: 'MERGE',
  edges: 'EDGES',
  edges_done: 'EDGES',
  waiting: 'PAUSE',
  done: 'DONE',
  error: 'ERROR',
  result: 'RESULT',
}

const STAGE_COLORS: Record<string, string> = {
  start: 'var(--ink-3)',
  fetch: 'var(--accent)',
  fetch_done: 'var(--accent)',
  extract: '#6080c0',
  extract_done: '#6080c0',
  merge: '#8060c0',
  merge_done: '#8060c0',
  edges: '#4090a0',
  edges_done: '#4090a0',
  waiting: '#6080c0',
  done: 'var(--high)',
  error: 'var(--conflict)',
  result: 'var(--high)',
}

function EventRow({ event }: { event: PipelineEvent }) {
  const label = STAGE_LABELS[event.stage] ?? event.stage.toUpperCase()
  const color = STAGE_COLORS[event.stage] ?? 'var(--ink-3)'
  return (
    <div style={{ display: 'flex', gap: 10, padding: '3px 0', alignItems: 'baseline' }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 500,
        letterSpacing: '0.1em', color, minWidth: 52, flexShrink: 0,
      }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.4 }}>
        {event.message}
        {event.sources && event.stage === 'fetch_done' && (
          <span style={{ color: 'var(--ink-3)', marginLeft: 6 }}>
            — {event.sources.map(s => {
              try { return new URL(s.url).hostname } catch { return s.url }
            }).join(', ')}
          </span>
        )}
      </span>
    </div>
  )
}

interface Props {
  session: Session
}

export default function PipelineLog({ session }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session.events.length])

  const waitingEvent = session.status === 'waiting'
    ? session.events.findLast(e => e.stage === 'waiting')
    : null

  async function handleApprove(approved: boolean) {
    if (!waitingEvent || !session.requestId || !waitingEvent.pause_stage) return
    await approveStage(session.requestId, waitingEvent.pause_stage, approved)
  }

  return (
    <div style={{
      background: 'var(--bg)', border: '1px solid var(--border-2)',
      margin: '0 0 16px 0', overflow: 'hidden',
    }}>
      <div style={{
        padding: '8px 12px 6px',
        borderBottom: '1px solid var(--border-2)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span className="section-label">Pipeline Log</span>
        <div style={{ flex: 1 }} />
        <div className={`status-dot status-${session.status}`} />
      </div>

      <div style={{
        padding: '8px 12px', maxHeight: 200, overflowY: 'auto',
        fontFamily: 'var(--font-mono)',
      }}>
        {session.events
          .filter(e => e.message && e.stage !== 'result')
          .map((event, i) => <EventRow key={i} event={event} />)}
        <div ref={bottomRef} />
      </div>

      {waitingEvent && (
        <div style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--border-2)',
          background: 'rgba(96, 128, 192, 0.06)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#6080c0', letterSpacing: '0.06em', marginBottom: 2 }}>
              Paused — {waitingEvent.pause_stage}
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Review the data below, then approve or reject this stage.
            </div>
          </div>
          <button onClick={() => handleApprove(false)} className="danger" style={{ flexShrink: 0 }}>Reject</button>
          <button onClick={() => handleApprove(true)} style={{
            flexShrink: 0, background: '#3a5080', borderColor: '#3a5080', color: '#fff',
          }}>Approve</button>
        </div>
      )}
    </div>
  )
}
