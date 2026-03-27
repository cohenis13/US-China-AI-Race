'use client'

import React, { useEffect, useRef } from 'react'
import type { RadarDimension, Confidence } from '@/lib/data'

// ── Dimension metadata (matches first version exactly) ───────────────────────
const DIM_META: Record<string, { desc: string; conf: string }> = {
  'Frontier Models': {
    desc: 'Relative capability at the leading edge of foundation model development, including benchmark performance and architectural innovation.',
    conf: 'Medium confidence',
  },
  'Compute': {
    desc: 'GPU stock, cloud compute capacity, national data center footprint, and sovereign compute investment programs.',
    conf: 'High confidence',
  },
  'Adoption': {
    desc: 'Rate and scale of AI deployment across enterprise, government, and consumer applications domestically.',
    conf: 'Lower confidence',
  },
  'Diffusion': {
    desc: 'Speed of AI technology spread across economic sectors and partner geographies, including deployment infrastructure.',
    conf: 'Lower confidence',
  },
  'Energy': {
    desc: 'Available and planned electricity generation and grid capacity dedicated to AI and large-scale data center workloads.',
    conf: 'High confidence',
  },
  'Talent': {
    desc: 'AI researcher density, top-tier publication output, immigration dynamics, and elite-institution talent pipeline.',
    conf: 'Medium confidence',
  },
}

// ── Confidence → point radius ─────────────────────────────────────────────────
const DOT_R:  Record<Confidence, number> = { high: 7,   medium: 4.5, low: 3 }
const DOT_HR: Record<Confidence, number> = { high: 9,   medium: 6.5, low: 5 }

// ── Tooltip word-wrap helper ──────────────────────────────────────────────────
function wrapText(text: string, maxLen: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  words.forEach(w => {
    const candidate = line ? line + ' ' + w : w
    if (candidate.length > maxLen) { if (line) lines.push(line); line = w }
    else line = candidate
  })
  if (line) lines.push(line)
  return lines
}

// ── Main component ────────────────────────────────────────────────────────────
export default function CapabilityRadar({ data }: { data: RadarDimension[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    // Read CSS custom properties so the chart respects the app's colour theme
    const style    = getComputedStyle(document.documentElement)
    const usHSL    = style.getPropertyValue('--us').trim()
    const cnHSL    = style.getPropertyValue('--china').trim()
    const muteHSL  = style.getPropertyValue('--muted-foreground').trim()
    const borderHSL = style.getPropertyValue('--border').trim()

    const usColor     = `hsl(${usHSL})`
    const cnColor     = `hsl(${cnHSL})`
    const muteColor   = `hsl(${muteHSL})`
    const borderColor = `hsl(${borderHSL})`

    const labels = data.map(d => d.dimension)
    const usData = data.map(d => d.US)
    const cnData = data.map(d => d.CN)
    const ptR    = data.map(d => DOT_R[d.confidence])
    const ptHR   = data.map(d => DOT_HR[d.confidence])

    // Dynamic import keeps chart.js out of the SSR bundle
    import('chart.js/auto').then(({ Chart }) => {
      if (!canvasRef.current) return  // component may have unmounted

      if (chartRef.current) {
        chartRef.current.destroy()
        chartRef.current = null
      }

      chartRef.current = new Chart(canvas, {
        type: 'radar',
        data: {
          labels,
          datasets: [
            {
              label: 'United States',
              data: usData,
              backgroundColor: `hsl(${usHSL} / 12%)`,
              borderColor: usColor, borderWidth: 2.5,
              pointBackgroundColor: usColor,
              pointBorderColor: 'rgba(255,255,255,0.85)', pointBorderWidth: 1.5,
              pointRadius: ptR, pointHoverRadius: ptHR,
              pointHoverBackgroundColor: usColor,
            },
            {
              label: 'China',
              data: cnData,
              backgroundColor: `hsl(${cnHSL} / 9%)`,
              borderColor: cnColor, borderWidth: 2.5,
              pointBackgroundColor: cnColor,
              pointBorderColor: 'rgba(255,255,255,0.85)', pointBorderWidth: 1.5,
              pointRadius: ptR, pointHoverRadius: ptHR,
              pointHoverBackgroundColor: cnColor,
            },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: true, aspectRatio: 1,
          interaction: { mode: 'nearest', intersect: true },
          scales: {
            r: {
              min: 0, max: 10,
              ticks: {
                stepSize: 2, color: muteColor,
                font: { size: 9 }, backdropColor: 'transparent',
              },
              grid:        { color: borderColor },
              angleLines:  { color: borderColor },
              pointLabels: {
                color: muteColor,
                font: { size: 11, weight: 600 },
                padding: 6,
              },
            },
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: 'rgba(8,18,32,0.97)',
              titleColor: '#dde5ee', bodyColor: '#7a97b0',
              borderColor: 'rgba(255,255,255,0.08)', borderWidth: 1,
              padding: { x: 14, y: 12 }, cornerRadius: 5,
              titleFont: { size: 12, weight: 'bold' as const },
              bodyFont: { size: 11 },
              callbacks: {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                title: (items: any[]) => items[0].label,
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                label: (ctx: any) => ' ' + ctx.dataset.label + ':\u00a0\u00a0' + ctx.parsed.r + ' / 10',
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                afterBody: (items: any[]) => {
                  if (!items.length) return []
                  const meta = DIM_META[items[0].label]
                  if (!meta) return []
                  return ['', ...wrapText(meta.desc, 48), '', '\u25cf Confidence: ' + meta.conf]
                },
              },
            },
          },
        },
      })
    })

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Scores 0–10 across six strategic dimensions
        </p>
      </div>

      <canvas ref={canvasRef} />

      {/* Country legend (line style, matches first version) */}
      <div style={{ display: 'flex', gap: 20, justifyContent: 'center', marginTop: 12 }}>
        {([
          { label: 'United States', color: 'hsl(var(--us))' },
          { label: 'China',         color: 'hsl(var(--china))' },
        ] as const).map(({ label, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={{ width: 24, height: 3, backgroundColor: color, borderRadius: 2 }} />
            <span style={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Confidence legend (dot size) */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {([
          { label: 'High confidence',   r: 7,   opacity: 1    },
          { label: 'Medium confidence', r: 4.5, opacity: 0.75 },
          { label: 'Lower confidence',  r: 3,   opacity: 0.5  },
        ] as const).map(({ label, r, opacity }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <svg width={r * 2 + 2} height={r * 2 + 2}>
              <circle cx={r + 1} cy={r + 1} r={r}
                fill="hsl(var(--muted-foreground))" opacity={opacity} />
            </svg>
            <span style={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}>{label}</span>
          </div>
        ))}
      </div>

      <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
        Scores represent analyst consensus estimates. Higher = stronger relative position.
        Hover a dot to see country score, confidence, and data source notes.
      </p>
    </div>
  )
}
