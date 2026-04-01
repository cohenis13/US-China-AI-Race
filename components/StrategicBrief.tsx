import type { ScoreCardDimension } from '@/lib/data'

interface Props {
  currentRead: string
  dimensions: ScoreCardDimension[]
}

const confRank: Record<string, number> = { high: 2, medium: 1, low: 0 }

// Template functions — receive live dimension data so key magnitudes update automatically.
// Dimensions where the interpretation is about data quality (not magnitude) stay static.
const PLAIN_SUMMARY: Record<string, (d: ScoreCardDimension) => string> = {
  investment: (d) => {
    const ratio = Math.round(d.usScore / Math.max(d.cnScore, 0.1))
    return `The U.S. outspends China on AI roughly ${ratio}-to-1 in private capital and data center infrastructure.`
  },
  compute: (d) => {
    const pct = Math.round((d.usScore / 10) * 100)
    return `U.S. labs account for ~${pct}% of disclosed AI training compute, backed by dominant GPU infrastructure.`
  },
  frontier_models: (d) => {
    const pct = Math.round((d.usScore / 10) * 100)
    return `U.S. labs produce ~${pct}% of the world's leading AI models by capability and research output.`
  },
  diffusion: (d) => {
    const pct = Math.round((d.usScore / 10) * 100)
    return `U.S.-origin AI models and cloud platforms account for ~${pct}% of the combined global diffusion footprint.`
  },
  energy: (d) => {
    const leader = d.leader === 'CN' ? 'China' : 'the U.S.'
    return `${leader} leads on AI energy scaling capacity by ${d.delta.toFixed(1)} points — China's grid buildout is outpacing U.S. permitting and interconnection timelines.`
  },
  talent: (d) => {
    const leader = d.leader === 'CN' ? 'China' : 'the U.S.'
    return `${leader} leads on AI research output by ${d.delta.toFixed(1)} points — China leads on volume while the U.S. leads on the highest-impact work.`
  },
  // Adoption: uncertainty is about data comparability, not magnitude — keep static
  adoption: (_) =>
    'Adoption is the most uncertain dimension because comparable U.S.–China data are limited and methodology differs across sources — the score reflects directional proxies, not a definitive measure.',
}

export default function StrategicBrief({ currentRead, dimensions }: Props) {
  // Biggest US advantage: highest delta where US leads
  const usWins = [...dimensions.filter(d => d.leader === 'US')].sort((a, b) => b.delta - a.delta)
  const topUS  = usWins[0]

  // Biggest US vulnerability: China-led, prioritise high confidence then largest delta
  const cnWins = [...dimensions.filter(d => d.leader === 'CN')].sort((a, b) => {
    const dr = (confRank[b.confidence] ?? 0) - (confRank[a.confidence] ?? 0)
    return dr !== 0 ? dr : b.delta - a.delta
  })
  const topCN  = cnWins[0]

  // Biggest uncertainty: lowest confidence first, then largest delta
  const uncertain = [...dimensions].sort((a, b) => {
    const dr = (confRank[a.confidence] ?? 0) - (confRank[b.confidence] ?? 0)
    return dr !== 0 ? dr : b.delta - a.delta
  })
  const topUnc = uncertain[0]

  const summary = (dim: ScoreCardDimension) =>
    (PLAIN_SUMMARY[dim.id]?.(dim)) ?? `${dim.label}: score gap of ${dim.delta.toFixed(1)} points.`

  const items = [
    {
      color: 'hsl(var(--us))',
      label: 'Biggest U.S. Advantage',
      dim:   topUS ? `${topUS.label} — ${topUS.confidence} confidence`  : null,
      text:  topUS ? summary(topUS)  : '—',
    },
    {
      color: 'hsl(var(--china))',
      label: 'Biggest U.S. Vulnerability',
      dim:   topCN ? `${topCN.label} — ${topCN.confidence} confidence`  : null,
      text:  topCN ? summary(topCN)  : '—',
    },
    {
      color: '#d97706',
      label: 'Biggest Uncertainty',
      dim:   topUnc ? `${topUnc.label} — ${topUnc.confidence} confidence` : null,
      text:  topUnc ? summary(topUnc) : '—',
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
