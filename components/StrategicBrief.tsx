import type { ScoreCardDimension, RadarDimension } from '@/lib/data'

interface Props {
  currentRead: string
  dimensions: ScoreCardDimension[]
  radarData: RadarDimension[]
}

// First sentence of a caveat string (up to and including the first period)
function firstSentence(text: string): string {
  if (!text) return ''
  const end = text.indexOf('.')
  return end !== -1 ? text.slice(0, end + 1) : text
}

const confRank: Record<string, number> = { high: 2, medium: 1, low: 0 }

export default function StrategicBrief({ currentRead, dimensions, radarData }: Props) {
  // Map caveat text from radarData by dimension label
  const caveatByLabel: Record<string, string> = {}
  for (const r of radarData) caveatByLabel[r.dimension] = r.caveat ?? ''

  // Biggest US advantage: highest delta where US leads
  const usWins  = [...dimensions.filter(d => d.leader === 'US')].sort((a, b) => b.delta - a.delta)
  const topUS   = usWins[0]

  // Biggest US vulnerability: China-led, prioritise high confidence then largest delta
  const cnWins  = [...dimensions.filter(d => d.leader === 'CN')].sort((a, b) => {
    const dr = (confRank[b.confidence] ?? 0) - (confRank[a.confidence] ?? 0)
    return dr !== 0 ? dr : b.delta - a.delta
  })
  const topCN   = cnWins[0]

  // Biggest uncertainty: lowest confidence first, then largest delta
  const uncertain = [...dimensions].sort((a, b) => {
    const dr = (confRank[a.confidence] ?? 0) - (confRank[b.confidence] ?? 0)
    return dr !== 0 ? dr : b.delta - a.delta
  })
  const topUnc  = uncertain[0]

  const items = [
    {
      color: 'hsl(var(--us))',
      label: 'Biggest U.S. Advantage',
      dim: topUS   ? `${topUS.label} — ${topUS.confidence} confidence`   : null,
      text: topUS   ? firstSentence(caveatByLabel[topUS.label])   || `U.S. ${topUS.usScore.toFixed(1)} vs China ${topUS.cnScore.toFixed(1)} — gap of ${topUS.delta.toFixed(1)} pts.`   : '—',
    },
    {
      color: 'hsl(var(--china))',
      label: 'Biggest U.S. Vulnerability',
      dim: topCN   ? `${topCN.label} — ${topCN.confidence} confidence`   : null,
      text: topCN   ? firstSentence(caveatByLabel[topCN.label])   || `China ${topCN.cnScore.toFixed(1)} vs U.S. ${topCN.usScore.toFixed(1)} — gap of ${topCN.delta.toFixed(1)} pts.`   : '—',
    },
    {
      color: '#d97706',
      label: 'Biggest Uncertainty',
      dim: topUnc  ? `${topUnc.label} — ${topUnc.confidence} confidence` : null,
      text: topUnc  ? firstSentence(caveatByLabel[topUnc.label])  || 'Scores based on limited or asymmetric data — treat as directional.' : '—',
    },
  ]

  return (
    <div className="bg-card border border-border rounded-xl shadow-sm p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold tracking-widest uppercase text-muted-foreground">
          Strategic Brief
        </span>
      </div>

      {/* Current read */}
      {currentRead && (
        <p className="text-sm text-foreground leading-relaxed mb-4 max-w-3xl">
          {currentRead}
        </p>
      )}

      {/* Three-column grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {items.map(({ color, label, dim, text }) => (
          <div
            key={label}
            className="bg-muted/40 border border-border rounded-lg p-3"
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-[9.5px] font-bold tracking-widest uppercase text-muted-foreground">
                {label}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">{text}</p>
            {dim && (
              <p className="text-[9px] font-semibold tracking-wide uppercase text-muted-foreground/60 mt-1.5">
                {dim}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
