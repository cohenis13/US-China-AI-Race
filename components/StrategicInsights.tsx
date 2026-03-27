import type { StrategicInsight } from '@/lib/data'

export default function StrategicInsights({ insights }: { insights: StrategicInsight[] }) {
  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm flex flex-col h-full">
      {/* FT-style header strip */}
      <div className="flex items-center gap-2 mb-5">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: 'hsl(var(--us))' }} />
        <h2 className="text-sm font-semibold text-foreground">Strategic Insights</h2>
        <span className="text-xs text-muted-foreground ml-1">Key findings for policymakers</span>
      </div>

      <ul className="flex flex-col flex-1" style={{ listStyle: 'none' }}>
        {insights.map((insight, i) => (
          <li
            key={i}
            className="text-sm text-muted-foreground leading-relaxed"
            style={{
              position: 'relative',
              padding: '12px 0 12px 20px',
              borderBottom: i < insights.length - 1 ? '1px solid hsl(var(--border))' : 'none',
            }}
          >
            {/* bullet dot */}
            <span style={{
              position: 'absolute', left: 0, top: 20,
              width: 6, height: 6, borderRadius: '50%',
              backgroundColor: 'hsl(var(--muted-foreground))',
              display: 'inline-block',
            }} />
            <strong className="text-foreground font-semibold">{insight.bold}</strong>
            {insight.rest}
          </li>
        ))}
      </ul>

      <div className="mt-6 pt-4 border-t border-border">
        <p className="text-xs text-muted-foreground leading-relaxed">
          Based on public disclosures, academic publications, and analyst estimates as of Q1 2026.
          All scores are directional.
        </p>
      </div>
    </div>
  )
}
