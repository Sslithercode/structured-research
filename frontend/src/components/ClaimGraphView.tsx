import { GraphCanvas, lightTheme, Sphere, Label } from 'reagraph'
import type { ClaimGraph, Claim } from '../types'

interface Props {
  graph: ClaimGraph
  onSelectClaim?: (claim: Claim | null) => void
  selectedClaimId?: string | null
}

const TIER_COLORS: Record<string, string> = {
  high:   '#3d8c5e',
  medium: '#c8921a',
  low:    '#9e3a3a',
}

const EDGE_COLORS: Record<string, string> = {
  supports:    '#3d8c5e',
  contradicts: '#9e3a3a',
  qualifies:   '#6a8ee0',
}

const theme = {
  ...lightTheme,
  canvas: { ...lightTheme.canvas, background: '#fafaf8' },
  node: {
    ...lightTheme.node,
    label: {
      ...lightTheme.node.label,
      color: '#1a1a1a',
      activeColor: '#1a1a1a',
      fontSize: 8,
    },
  },
  edge: {
    ...lightTheme.edge,
    label: {
      ...lightTheme.edge.label,
      color: '#666660',
      activeColor: '#666660',
      fontSize: 6,
    },
  },
}

export default function ClaimGraphView({ graph, onSelectClaim, selectedClaimId }: Props) {
  const sourceMap = new Map(graph.sources.map(s => [s.source_id, s]))

  const nodes = graph.claims.map(claim => {
    const source = sourceMap.get(claim.source_id)
    const tier = source?.reliability_tier ?? 'medium'
    return {
      id: claim.claim_id,
      label: claim.text.length > 55 ? claim.text.slice(0, 52) + '…' : claim.text,
      fill: TIER_COLORS[tier] ?? '#555',
    }
  })

  const edges = graph.edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.from_claim,
    target: e.to_claim,
    label: e.type,
    fill: EDGE_COLORS[e.type] ?? '#888',
  }))

  const selections = selectedClaimId ? [selectedClaimId] : []

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        selections={selections}
        theme={theme}
        cameraMode="pan"
        layoutType="forceDirected2d"
        edgeInterpolation="curved"
        labelType="none"
        renderNode={({ node, color, size, opacity }) => (
          <>
            <Sphere node={node} color={color} size={size} opacity={opacity} />
            <group position={[0, -(size + 3), node.position?.z ?? 0]}>
              <Label
                text={node.label ?? ''}
                fontSize={7}
                color="#1a1a1a"
                stroke="#fafaf8"
                opacity={opacity}
              />
            </group>
          </>
        )}
        onNodeClick={(node) => {
          const claim = graph.claims.find(c => c.claim_id === node.id) ?? null
          onSelectClaim?.(claim)
        }}
        onCanvasClick={() => onSelectClaim?.(null)}
      />

      <div style={{
        position: 'absolute', bottom: 12, left: 12,
        background: '#ffffff', border: '1px solid #e0ddd6',
        padding: '8px 10px', fontSize: 9, fontFamily: 'var(--font-mono)',
        color: '#666', display: 'flex', flexDirection: 'column', gap: 4,
        pointerEvents: 'none', borderRadius: 4,
      }}>
        <div style={{ color: '#333', marginBottom: 2, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}>Legend</div>
        {Object.entries(TIER_COLORS).map(([tier, color]) => (
          <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
            {tier} reliability
          </div>
        ))}
        <div style={{ borderTop: '1px solid #e0ddd6', marginTop: 2, paddingTop: 4 }}>
          {Object.entries(EDGE_COLORS).map(([type, color]) => (
            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 2 }}>
              <div style={{ width: 14, height: 2, background: color, borderRadius: 1 }} />
              {type}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
