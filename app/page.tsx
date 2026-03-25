import ScoreCardStrip from '@/components/ScoreCardStrip'
import CapabilityRadar from '@/components/CapabilityRadar'
import StrategicInsights from '@/components/StrategicInsights'
import DimensionTabs from '@/components/DimensionTabs'
import {
  scorecardDimensions,
  radarData,
  strategicInsights,
  dimensionTabs,
} from '@/lib/data'

export default function Dashboard() {
  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">

        {/* ── Hero Header ────────────────────────────────────── */}
        <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-foreground tracking-tight text-balance">
              U.S. vs China AI Race
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Strategic Capability Tracker &mdash; Q1 2026
            </p>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 shrink-0 pb-0.5">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: 'hsl(var(--us))' }} />
              <span className="text-xs font-medium text-muted-foreground">United States</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: 'hsl(var(--china))' }} />
              <span className="text-xs font-medium text-muted-foreground">China</span>
            </div>
            <div className="flex items-center gap-3 pl-3 border-l border-border">
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-[10px] text-muted-foreground">High</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-[10px] text-muted-foreground">Med</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-zinc-400" />
                <span className="text-[10px] text-muted-foreground">Low</span>
              </div>
              <span className="text-[10px] text-muted-foreground italic">confidence</span>
            </div>
          </div>
        </header>

        {/* ── Scorecard Strip ────────────────────────────────── */}
        <section aria-label="Scorecard">
          <ScoreCardStrip dimensions={scorecardDimensions} />
        </section>

        {/* ── Main Grid: Radar + Insights ────────────────────── */}
        <section
          aria-label="Capability overview and strategic insights"
          className="grid grid-cols-1 lg:grid-cols-5 gap-6"
        >
          <div className="lg:col-span-3">
            <CapabilityRadar data={radarData} />
          </div>
          <div className="lg:col-span-2">
            <StrategicInsights insights={strategicInsights} />
          </div>
        </section>

        {/* ── Dimension Tabs ─────────────────────────────────── */}
        <section aria-label="Dimension analysis">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground">Dimension Deep-Dive</h2>
            <span className="text-xs text-muted-foreground">Select a dimension to explore</span>
          </div>
          <DimensionTabs tabs={dimensionTabs} />
        </section>

        {/* ── Footer ─────────────────────────────────────────── */}
        <footer className="pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground leading-relaxed">
            Data sourced from public disclosures, academic benchmarks, industry reports, and analyst estimates.
            All scores are directional and subject to revision.{' '}
            <button className="underline underline-offset-2 hover:text-foreground transition-colors">
              Methodology
            </button>
          </p>
        </footer>

      </div>
    </main>
  )
}
