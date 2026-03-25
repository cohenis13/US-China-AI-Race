import type { ReactNode } from 'react'

export default function StrategicInsights({ insights }: { insights: string[] }) {
  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm flex flex-col h-full">
      {/* FT-style header strip */}
      <div className="flex items-center gap-2 mb-5">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: 'hsl(var(--us))' }} />
        <h2 className="text-sm font-semibold text-foreground">Strategic Insights</h2>
      </div>

      <ul className="flex flex-col gap-4 flex-1">
        {insights.map((insight, i) => (
          <li key={i} className="flex items-start gap-3">
            <span
              className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: 'hsl(var(--us))' }}
            />
            <p className="text-sm text-foreground leading-relaxed">{insight}</p>
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
