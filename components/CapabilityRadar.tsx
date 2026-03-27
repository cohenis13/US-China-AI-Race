'use client'

import React, { useState, useRef, useCallback, useEffect } from 'react'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { RadarDimension, Confidence } from '@/lib/data'

// ── Constants (must match RadarChart props below) ─────────────────────────────
const CHART_H  = 300
const OUTER_R  = 100   // outerRadius passed to RadarChart
const MARGIN   = { top: 10, right: 20, bottom: 10, left: 20 }
// cy is fixed regardless of container width (symmetric top/bottom margins)
const CY = (CHART_H - MARGIN.top - MARGIN.bottom) / 2 + MARGIN.top  // = 150

// ── Confidence sizing ─────────────────────────────────────────────────────────
const DOT_R: Record<Confidence, number>       = { high: 7, medium: 4.5, low: 3 }
const DOT_OPACITY: Record<Confidence, number> = { high: 1, medium: 0.75, low: 0.5 }
const CONF_LABEL: Record<Confidence, string>  = {
  high:   'High confidence',
  medium: 'Medium confidence',
  low:    'Lower confidence',
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface HoverState {
  x: number; y: number
  dimension: string; value: number
  country: 'US' | 'CN'; confidence: Confidence; caveat: string
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function RadarTooltipBox({ hover, containerW }: { hover: HoverState; containerW: number }) {
  const TOOLTIP_W = 240
  const OFFSET    = 14

  let left: number | undefined
  let right: number | undefined
  let top: number | undefined
  let bottom: number | undefined

  if (hover.x > containerW / 2) {
    right = Math.max(containerW - hover.x + OFFSET, 4)
  } else {
    left = Math.min(hover.x + OFFSET, containerW - TOOLTIP_W - 4)
  }
  if (hover.y > CHART_H / 2) {
    bottom = Math.max(CHART_H - hover.y + OFFSET, 4)
  } else {
    top = hover.y + OFFSET
  }

  const countryColor = hover.country === 'US' ? 'hsl(var(--us))' : 'hsl(var(--china))'
  const countryLabel = hover.country === 'US' ? 'United States' : 'China'

  return (
    <div style={{
      position: 'absolute', left, right, top, bottom,
      width: TOOLTIP_W,
      background: 'hsl(var(--card))',
      border: '1px solid hsl(var(--border))',
      borderRadius: 8, padding: '10px 14px',
      fontSize: 12, lineHeight: 1.5,
      color: 'hsl(var(--foreground))',
      boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
      pointerEvents: 'none', zIndex: 50,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{hover.dimension}</div>
      <div style={{ marginBottom: 6 }}>
        <span style={{ color: countryColor, fontWeight: 600 }}>{countryLabel}:</span>
        {' '}{hover.value.toFixed(1)} / 10
      </div>
      <div style={{ color: 'hsl(var(--muted-foreground))', fontWeight: 500, marginBottom: hover.caveat ? 5 : 0 }}>
        ● {CONF_LABEL[hover.confidence]}
      </div>
      {hover.caveat && (
        <div style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11, lineHeight: 1.4 }}>
          {hover.caveat}
        </div>
      )}
    </div>
  )
}

// ── Dot overlay ───────────────────────────────────────────────────────────────
// Rendered as a separate absolutely-positioned SVG on top of the Recharts SVG.
// Positions are computed from the same math Recharts uses internally,
// so dots align perfectly with the polygon endpoints.
function DotOverlay({ data, chartW, onEnter, onLeave }: {
  data: RadarDimension[]
  chartW: number
  onEnter: (s: HoverState, e: React.MouseEvent<SVGCircleElement>) => void
  onLeave: () => void
}) {
  const n  = data.length
  const cx = chartW / 2  // symmetric left/right margins → center = half width

  return (
    <svg
      style={{
        position: 'absolute', top: 0, left: 0,
        width: chartW, height: CHART_H,
        overflow: 'visible',
        pointerEvents: 'none',   // overlay itself is transparent
      }}
    >
      {data.map((d, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        const cosA  = Math.cos(angle)
        const sinA  = Math.sin(angle)
        const conf  = d.confidence ?? 'low'
        const r     = DOT_R[conf]
        const op    = DOT_OPACITY[conf]
        const usR   = (d.US / 10) * OUTER_R
        const cnR   = (d.CN / 10) * OUTER_R
        const usX   = cx + usR * cosA
        const usY   = CY + usR * sinA
        const cnX   = cx + cnR * cosA
        const cnY   = CY + cnR * sinA
        const hitR  = Math.max(r + 8, 12)

        return (
          <g key={d.dimension}>
            {/* US dot */}
            <circle cx={usX} cy={usY} r={r} fill="hsl(var(--us))" opacity={op} />
            <circle
              cx={usX} cy={usY} r={hitR}
              fill="rgba(0,0,0,0)"
              style={{ pointerEvents: 'all', cursor: 'pointer' }}
              onMouseEnter={(e) => onEnter({
                x: 0, y: 0,   // overwritten by parent onMouseMove
                dimension: d.dimension, value: d.US,
                country: 'US', confidence: conf, caveat: d.caveat ?? '',
              }, e)}
              onMouseLeave={onLeave}
            />
            {/* CN dot */}
            <circle cx={cnX} cy={cnY} r={r} fill="hsl(var(--china))" opacity={op} />
            <circle
              cx={cnX} cy={cnY} r={hitR}
              fill="rgba(0,0,0,0)"
              style={{ pointerEvents: 'all', cursor: 'pointer' }}
              onMouseEnter={(e) => onEnter({
                x: 0, y: 0,
                dimension: d.dimension, value: d.CN,
                country: 'CN', confidence: conf, caveat: d.caveat ?? '',
              }, e)}
              onMouseLeave={onLeave}
            />
          </g>
        )
      })}
    </svg>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function CapabilityRadar({ data }: { data: RadarDimension[] }) {
  const [hover, setHover]   = useState<HoverState | null>(null)
  const [chartW, setChartW] = useState(0)
  const containerRef        = useRef<HTMLDivElement>(null)
  const mousePos            = useRef({ x: 0, y: 0 })

  // Track container width so the overlay can compute dot positions
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setChartW(el.offsetWidth))
    ro.observe(el)
    setChartW(el.offsetWidth)
    return () => ro.disconnect()
  }, [])

  // Track cursor position on the wrapper (more reliable than SVG event coords)
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    mousePos.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }, [])

  // Dot enter: inject the latest cursor position
  const handleDotEnter = useCallback((info: HoverState) => {
    setHover({ ...info, x: mousePos.current.x, y: mousePos.current.y })
  }, [])

  const handleDotLeave = useCallback(() => setHover(null), [])

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Scores 0–10 across six strategic dimensions</p>
      </div>

      {/* Chart wrapper — position:relative anchors the overlay and tooltip */}
      <div
        ref={containerRef}
        style={{ position: 'relative' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleDotLeave}
      >
        <ResponsiveContainer width="100%" height={CHART_H}>
          <RadarChart
            data={data}
            margin={MARGIN}
            outerRadius={OUTER_R}
          >
            <PolarGrid stroke="hsl(var(--border))" strokeDasharray="3 3" strokeWidth={0.8} />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11, fontFamily: 'var(--font-inter)' }}
              tickLine={false}
            />
            {/* dot={false} — dots are drawn by DotOverlay instead */}
            <Radar
              name="United States"
              dataKey="US"
              stroke="hsl(var(--us))"
              fill="hsl(var(--us))"
              fillOpacity={0.18}
              strokeWidth={2}
              dot={false}
              activeDot={false}
            />
            <Radar
              name="China"
              dataKey="CN"
              stroke="hsl(var(--china))"
              fill="hsl(var(--china))"
              fillOpacity={0.14}
              strokeWidth={2}
              dot={false}
              activeDot={false}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              formatter={(value) => (
                <span style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>{value}</span>
              )}
            />
          </RadarChart>
        </ResponsiveContainer>

        {/* Dot overlay — separate SVG, no Recharts involvement */}
        {chartW > 0 && (
          <DotOverlay
            data={data}
            chartW={chartW}
            onEnter={handleDotEnter}
            onLeave={handleDotLeave}
          />
        )}

        {/* Tooltip */}
        {hover && (
          <RadarTooltipBox hover={hover} containerW={chartW || 400} />
        )}
      </div>

      {/* Confidence legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {(['high', 'medium', 'low'] as Confidence[]).map((conf) => {
          const r = DOT_R[conf]
          return (
            <div key={conf} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width={r * 2 + 2} height={r * 2 + 2}>
                <circle cx={r + 1} cy={r + 1} r={r}
                  fill="hsl(var(--muted-foreground))" opacity={DOT_OPACITY[conf]} />
              </svg>
              <span style={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}>{CONF_LABEL[conf]}</span>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
        Scores represent analyst consensus estimates. Higher = stronger relative position.
        Hover a dot to see country score, confidence, and data source notes.
      </p>
    </div>
  )
}
