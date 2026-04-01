import type { ScoreCardDimension } from '@/lib/data'

interface Props {
  currentRead: string
  dimensions: ScoreCardDimension[]
}

const confRank: Record<string, number> = { high: 2, medium: 1, low: 0 }

// Plain-English one-sentence summaries per dimension ID.
// These replace technical caveat text in the brief.
const PLAIN_SUMMARY: Record<string, string> = {
  investment:      'The U.S. outspends China on AI roughly 10-to-1 in private capital and data center infrastructure.',
  compute:         'U.S. labs control the vast majority of disclosed AI training compute, backed by dominant GPU infrastructure.',
  frontier_models: 'U.S. labs produce most of the world\'s leading AI models by capability and research output.',
  diffusion:       'U.S.-origin AI models and cloud platforms reach far more countries and users globally than China\'s.',
  energy:          'China is building power grid and data center capacity far faster than the U.S., which is held back by permitting delays and grid backlogs.',
  talent:          'China produces more AI research by volume; the U.S. leads on the highest-impact work and attracts global talent.',
  adoption:        'We lack clean comparable data on how widely AI is used inside Chinese vs. American businesses — the best available estimate is a single 2024 survey.',
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
    PLAIN_SUMMARY[dim.id] ?? `${dim.label}: score gap of ${dim.delta.toFixed(1)} points.`

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
