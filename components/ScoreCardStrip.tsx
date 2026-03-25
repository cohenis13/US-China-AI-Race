'use client'

import clsx from 'clsx'
import type { ScoreCardDimension, Confidence } from '@/lib/data'

const confidenceColors: Record<Confidence, string> = {
  high:   'bg-emerald-500',
  medium: 'bg-amber-400',
  low:    'bg-zinc-400',
}

const confidenceLabels: Record<Confidence, string> = {
  high:   'High confidence',
  medium: 'Medium confidence',
  low:    'Low confidence',
}

function ScoreBar({ us, cn }: { us: number; cn: number }) {
  const max = 10
  return (
    <div className="flex gap-1 items-center w-full mt-2">
      <div
        className="h-1.5 rounded-full"
        style={{ width: `${(us / max) * 100}%`, backgroundColor: 'hsl(var(--us))' }}
        title={`US: ${us}`}
      />
      <div
        className="h-1.5 rounded-full opacity-70"
        style={{ width: `${(cn / max) * 100}%`, backgroundColor: 'hsl(var(--china))' }}
        title={`CN: ${cn}`}
      />
    </div>
  )
}

export default function ScoreCardStrip({ dimensions }: { dimensions: ScoreCardDimension[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {dimensions.map((d) => {
        const usLeads = d.leader === 'US'
        const cnLeads = d.leader === 'CN'
        return (
          <div
            key={d.id}
            className="bg-card rounded-xl border border-border p-4 shadow-sm hover:shadow-md transition-shadow duration-200 flex flex-col gap-2"
          >
            {/* Dimension label + confidence dot */}
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide leading-tight">
                {d.label}
              </span>
              <span
                className={clsx('w-2 h-2 rounded-full shrink-0', confidenceColors[d.confidence])}
                title={confidenceLabels[d.confidence]}
              />
            </div>

            {/* Scores row */}
            <div className="flex items-end justify-between gap-1">
              <div className="flex flex-col items-start">
                <span className="text-[10px] text-muted-foreground">US</span>
                <span
                  className={clsx(
                    'text-2xl font-bold leading-none tabular-nums',
                    usLeads ? 'text-foreground' : 'text-muted-foreground'
                  )}
                  style={usLeads ? { color: 'hsl(var(--us))' } : undefined}
                >
                  {d.usScore}
                </span>
              </div>

              {/* Delta badge */}
              <div
                className={clsx(
                  'text-[10px] font-semibold px-1.5 py-0.5 rounded-md leading-none',
                  usLeads
                    ? 'text-card'
                    : 'text-card'
                )}
                style={{
                  backgroundColor: usLeads ? 'hsl(var(--us))' : 'hsl(var(--china))',
                }}
              >
                +{d.delta} {d.leader}
              </div>

              <div className="flex flex-col items-end">
                <span className="text-[10px] text-muted-foreground">CN</span>
                <span
                  className={clsx(
                    'text-2xl font-bold leading-none tabular-nums',
                    cnLeads ? 'text-foreground' : 'text-muted-foreground'
                  )}
                  style={cnLeads ? { color: 'hsl(var(--china))' } : undefined}
                >
                  {d.cnScore}
                </span>
              </div>
            </div>

            {/* Mini bar */}
            <ScoreBar us={d.usScore} cn={d.cnScore} />
          </div>
        )
      })}
    </div>
  )
}
