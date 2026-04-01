import type { ScoreCardDimension } from '@/lib/data'

interface Props {
  currentRead: string
  dimensions: ScoreCardDimension[]
}

const confRank: Record<string, number> = { high: 2, medium: 1, low: 0 }

// Strategic labels used in the current-read sentence (replaces raw dimension names)
const STRATEGIC_LABEL: Record<string, string> = {
  investment:      'capital',
  compute:         'compute',
  frontier_models: 'frontier model development',
  diffusion:       'global deployment',
  talent:          'research talent',
  energy:          'energy capacity',
  adoption:        'domestic adoption',
}

function naturalJoin(items: string[]): string {
  if (items.length === 0) return ''
  if (items.length === 1) return items[0]
  return items.slice(0, -1).join(', ') + ', and ' + items[items.length - 1]
}

// Builds the top-line summary from live dimension data, bypassing the stale
// pipeline-generated current_read string.
function buildCurrentRead(dimensions: ScoreCardDimension[]): string {
  const usWins = [...dimensions.filter(d => d.leader === 'US')].sort((a, b) => b.delta - a.delta)
  const cnWins = [...dimensions.filter(d => d.leader === 'CN')].sort((a, b) => b.delta - a.delta)

  const label = (d: ScoreCardDimension) => STRATEGIC_LABEL[d.id] ?? d.label.toLowerCase()

  const clauses: string[] = []
  if (usWins.length > 0)
    clauses.push('The U.S. leads in ' + naturalJoin(usWins.map(label)))
  if (cnWins.length > 0)
    clauses.push((clauses.length > 0 ? 'while China leads in ' : 'China leads in ') + naturalJoin(cnWins.map(label)))

  return clauses.length > 0 ? clauses.join(', ') + '.' : ''
}

// Template functions for the Advantage and Vulnerability cards — interpolate live scores.
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
  adoption: (_) =>
    'China shows stronger adoption on available proxies, driven largely by industrial automation density. Enterprise survey rates are broadly comparable between the two countries.',
}

// Uncertainty-framing sentences for the Biggest Uncertainty card.
// These explain WHY confidence is low, not the score magnitude.
const UNCERTAINTY_SUMMARY: Record<string, string> = {
  diffusion:       'Diffusion confidence is limited — private model deployments, government usage, and unreported inference are largely invisible, making global footprint comparisons directional at best.',
  adoption:        'Adoption is uncertain because comparable U.S.–China data are scarce and methodology differs across sources — the score reflects directional proxies, not a definitive measure.',
  frontier_models: 'Frontier model rankings shift quickly and Chinese capability may be undercounted in public benchmarks — the scored gap could be narrower than it appears.',
  talent:          'Talent is hard to measure precisely — volume metrics favor China while quality metrics favor the U.S., and the true effective talent pool in each country is unknown.',
  compute:         'Compute estimates rely on disclosed specs and public GPU sales, which likely undercount classified and government deployments in both countries.',
  energy:          'Energy capacity projections carry uncertainty — planned buildout depends on permitting timelines and grid investment decisions that frequently shift.',
  investment:      'Investment figures reflect disclosed deals and public filings, which likely undercount government-directed investment in China and stealth R&D in both countries.',
}

export default function StrategicBrief({ dimensions }: Props) {
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

  const plainSummary = (dim: ScoreCardDimension) =>
    (PLAIN_SUMMARY[dim.id]?.(dim)) ?? `${dim.label}: score gap of ${dim.delta.toFixed(1)} points.`

  const uncSummary = (dim: ScoreCardDimension) =>
    UNCERTAINTY_SUMMARY[dim.id] ?? `${dim.label} has ${dim.confidence} confidence — treat this score as directional.`

  const currentRead = buildCurrentRead(dimensions)

  const items = [
    {
      color: 'hsl(var(--us))',
      label: 'Biggest U.S. Advantage',
      dim:   topUS ? `${topUS.label} — ${topUS.confidence} confidence`  : null,
      text:  topUS ? plainSummary(topUS)  : '—',
    },
    {
      color: 'hsl(var(--china))',
      label: 'Biggest U.S. Vulnerability',
      dim:   topCN ? `${topCN.label} — ${topCN.confidence} confidence`  : null,
      text:  topCN ? plainSummary(topCN)  : '—',
    },
    {
      color: '#d97706',
      label: 'Biggest Uncertainty',
      dim:   topUnc ? `${topUnc.label} — ${topUnc.confidence} confidence` : null,
      text:  topUnc ? uncSummary(topUnc) : '—',
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
