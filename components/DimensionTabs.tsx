'use client'

import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from 'recharts'
import clsx from 'clsx'
import type { DimensionTab, AdoptionSignal, DimensionSource } from '@/lib/data'

const METHODOLOGY_URL = 'https://us-china-ai-race.vercel.app/docs/methodology.html'

const statusStyles: Record<AdoptionSignal['usStatus'], string> = {
  'OK':       'bg-emerald-50 text-emerald-700 border border-emerald-200',
  'PARTIAL':  'bg-amber-50 text-amber-700 border border-amber-200',
  'NO DATA':  'bg-zinc-100 text-zinc-500 border border-zinc-200',
}

function AdoptionTable({ signals }: { signals: AdoptionSignal[] }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground italic">
        Coverage limited — compare directionally
      </p>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 border-b border-border">
              <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground w-1/3">Signal</th>
              <th className="text-center px-4 py-2.5 text-xs font-medium" style={{ color: 'hsl(var(--us))' }}>United States</th>
              <th className="text-center px-4 py-2.5 text-xs font-medium" style={{ color: 'hsl(var(--china))' }}>China</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s, i) => (
              <tr key={i} className={clsx('border-b border-border last:border-0', i % 2 === 1 && 'bg-muted/20')}>
                <td className="px-4 py-3">
                  <div className="font-medium text-foreground text-sm">{s.signal}</div>
                  {s.note && <div className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{s.note}</div>}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-md', statusStyles[s.usStatus])}>
                    {s.usStatus}
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-md', statusStyles[s.cnStatus])}>
                    {s.cnStatus}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DimensionBarChart({ data, xLabel }: { data: { label: string; US: number; CN: number }[]; xLabel?: string }) {
  // Flatten to grouped horizontal bar-friendly format
  const transformed = data.flatMap((d) => [
    { label: d.label, country: 'US', value: d.US },
    { label: d.label, country: 'CN', value: d.CN },
  ])

  // Build pairs for side-by-side display
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.label} className="space-y-1">
          <div className="text-xs text-muted-foreground font-medium">{d.label}</div>
          <div className="flex flex-col gap-0.5">
            {/* US bar */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] w-5 shrink-0 font-semibold" style={{ color: 'hsl(var(--us))' }}>US</span>
              <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(d.US, 100)}%`, backgroundColor: 'hsl(var(--us))' }}
                />
              </div>
              <span className="text-[10px] tabular-nums text-muted-foreground w-6 text-right">{d.US}</span>
            </div>
            {/* CN bar */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] w-5 shrink-0 font-semibold" style={{ color: 'hsl(var(--china))' }}>CN</span>
              <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(d.CN, 100)}%`, backgroundColor: 'hsl(var(--china))' }}
                />
              </div>
              <span className="text-[10px] tabular-nums text-muted-foreground w-6 text-right">{d.CN}</span>
            </div>
          </div>
        </div>
      ))}
      {xLabel && (
        <p className="text-xs text-muted-foreground mt-2 italic">{xLabel}</p>
      )}
    </div>
  )
}

function ComparisonTable({ rows }: { rows: { label: string; us: string; cn: string }[] }) {
  return (
    <div className="rounded-lg border border-border overflow-hidden mt-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/60 border-b border-border">
            <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground w-1/3"></th>
            <th className="text-left px-4 py-2 text-xs font-semibold" style={{ color: 'hsl(var(--us))' }}>United States</th>
            <th className="text-left px-4 py-2 text-xs font-semibold" style={{ color: 'hsl(var(--china))' }}>China</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={clsx('border-b border-border last:border-0', i % 2 === 1 && 'bg-muted/20')}>
              <td className="px-4 py-2.5 text-xs font-medium text-muted-foreground">{r.label}</td>
              <td className="px-4 py-2.5 text-sm text-foreground">{r.us}</td>
              <td className="px-4 py-2.5 text-sm text-foreground">{r.cn}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DimensionTabs({ tabs }: { tabs: DimensionTab[] }) {
  const [activeId, setActiveId] = useState(tabs[0].id)
  const active = tabs.find((t) => t.id === activeId) ?? tabs[0]

  return (
    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
      {/* Tab bar */}
      <div className="flex overflow-x-auto border-b border-border bg-muted/30">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveId(tab.id)}
            className={clsx(
              'px-4 py-3 text-xs font-medium whitespace-nowrap transition-colors duration-150 border-b-2 shrink-0',
              activeId === tab.id
                ? 'border-current text-foreground bg-card'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50'
            )}
            style={activeId === tab.id ? { borderBottomColor: 'hsl(var(--us))' } : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-6">
        {/* Headline */}
        <div className="mb-5">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-foreground leading-snug">
              {active.headline}
            </h3>
            {active.headlineNote && (
              <span className="text-xs text-muted-foreground">— {active.headlineNote}</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed max-w-2xl">
            {active.explanation}
          </p>
        </div>

        {/* Chart or adoption signals */}
        {active.adoptionSignals ? (
          <AdoptionTable signals={active.adoptionSignals} />
        ) : active.barData ? (
          <DimensionBarChart data={active.barData} xLabel={active.barXLabel} />
        ) : null}

        {/* Comparison table */}
        {active.tableRows && <ComparisonTable rows={active.tableRows} />}

        {/* Sources footer */}
        <div className="mt-5 pt-4 border-t border-border flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-muted-foreground">
          {active.sources && active.sources.length > 0 && (
            <>
              <span>Sources:</span>
              {active.sources.map((s: DimensionSource, i: number) => (
                <span key={s.url} className="inline-flex items-center gap-1.5">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2 hover:text-foreground transition-colors"
                  >
                    {s.label}
                  </a>
                  {i < (active.sources?.length ?? 0) - 1 && (
                    <span className="text-muted-foreground/50">·</span>
                  )}
                </span>
              ))}
              <span className="text-muted-foreground/50">·</span>
            </>
          )}
          <a
            href={METHODOLOGY_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-foreground transition-colors"
          >
            Full methodology →
          </a>
        </div>
      </div>
    </div>
  )
}
