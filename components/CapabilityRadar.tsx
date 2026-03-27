'use client'

import { useState, useRef, useCallback } from 'react'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { RadarDimension, Confidence } from '@/lib/data'

// ── Confidence sizing ─────────────────────────────────────────────────────────
// Matches first version: high=7px, medium=4.5px, low=3px
const DOT_R: Record<Confidence, number> = { high: 7, medium: 4.5, low: 3 }
const DOT_OPACITY: Record<Confidence, number> = { high: 1, medium: 0.75, low: 0.5 }

const CONF_LABEL: Record<Confidence, string> = {
  high:   'High confidence',
  medium: 'Medium confidence',
  low:    'Lower confidence',
}

// ── Hover state ───────────────────────────────────────────────────────────────
interface HoverState {
  /** Mouse position relative to the chart container */
  x: number
  y: number
  dimension: string
  value: number
  country: 'US' | 'CN'
  confidence: Confidence
  caveat: string
}

// ── Custom dot factory ────────────────────────────────────────────────────────
// Returns a render function for use in Recharts <Radar dot={…}>
// Each country gets its own factory so the closure captures the right fill/country.
function makeDotRenderer(
  country: 'US' | 'CN',
  fill: string,
  onEnter: (s: HoverState, e: React.MouseEvent) => void,
  onLeave: () => void,
) {
  // eslint-disable-next-line react/display-name
  return function DotRenderer(props: Record<string, unknown>) {
    const cx      = props.cx as number | undefined
    const cy      = props.cy as number | undefined
    const payload = props.payload as RadarDimension | undefined
    if (cx == null || cy == null || !payload) return null

    const conf    = payload.confidence ?? 'low'
    const r       = DOT_R[conf]
    const opacity = DOT_OPACITY[conf]
    const value   = country === 'US' ? payload.US : payload.CN

    return (
      <g>
        {/* Visible dot */}
        <circle cx={cx} cy={cy} r={r} fill={fill} opacity={opacity} stroke="none" />
        {/* Larger transparent hit area so thin dots are still easy to hover */}
        <circle
          cx={cx} cy={cy} r={Math.max(r + 8, 12)}
          fill="transparent"
          style={{ cursor: 'pointer' }}
          onMouseEnter={(e) =>
            onEnter(
              { x: 0, y: 0, dimension: payload.dimension, value, country, confidence: conf, caveat: payload.caveat ?? '' },
              e,
            )
          }
          onMouseLeave={onLeave}
        />
      </g>
    )
  }
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function RadarTooltipBox({
  hover,
  containerW,
  containerH,
}: {
  hover: HoverState
  containerW: number
  containerH: number
}) {
  const countryColor = hover.country === 'US' ? 'hsl(var(--us))' : 'hsl(var(--china))'
  const countryLabel = hover.country === 'US' ? 'United States' : 'China'

  // Position the tooltip near the cursor but keep it inside the container.
  // Flip horizontally / vertically so it never covers the chart centre.
  const TOOLTIP_W = 240
  const TOOLTIP_H_EST = 120
  const OFFSET = 14

  let left: number | undefined
  let right: number | undefined
  let top: number | undefined
  let bottom: number | undefined

  if (hover.x > containerW / 2) {
    right = containerW - hover.x + OFFSET
  } else {
    left = hover.x + OFFSET
  }
  // Clamp so the box doesn't go off-screen vertically
  if (hover.y > containerH / 2) {
    bottom = containerH - hover.y + OFFSET
  } else {
    top = hover.y + OFFSET
  }

  // Enforce a maximum left so it can't go off-right-edge
  if (left !== undefined && left + TOOLTIP_W > containerW) {
    left = containerW - TOOLTIP_W - 4
  }

  return (
    <div
      style={{
        position: 'absolute',
        left,
        right,
        top,
        bottom,
        width: TOOLTIP_W,
        background: 'hsl(var(--card))',
        border: '1px solid hsl(var(--border))',
        borderRadius: 8,
        padding: '10px 14px',
        fontSize: 12,
        lineHeight: 1.5,
        color: 'hsl(var(--foreground))',
        boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
        pointerEvents: 'none',
        zIndex: 50,
      }}
    >
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

// ── Main component ────────────────────────────────────────────────────────────
export default function CapabilityRadar({ data }: { data: RadarDimension[] }) {
  const [hover, setHover]     = useState<HoverState | null>(null)
  const containerRef          = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ w: 400, h: 300 })

  const handleEnter = useCallback((info: HoverState, e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    setContainerSize({ w: rect.width, h: rect.height })
    setHover({ ...info, x: e.clientX - rect.left, y: e.clientY - rect.top })
  }, [])

  const handleLeave = useCallback(() => setHover(null), [])

  const usDot = makeDotRenderer('US', 'hsl(var(--us))',     handleEnter, handleLeave)
  const cnDot = makeDotRenderer('CN', 'hsl(var(--china))', handleEnter, handleLeave)

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Scores 0–10 across six strategic dimensions</p>
      </div>

      {/* Chart wrapper — position:relative so the tooltip can be absolute inside it */}
      <div ref={containerRef} style={{ position: 'relative' }}>
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
            <PolarGrid
              stroke="hsl(var(--border))"
              strokeDasharray="3 3"
              strokeWidth={0.8}
            />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11, fontFamily: 'var(--font-inter)' }}
              tickLine={false}
            />
            {/* No <Tooltip> — we handle it ourselves above */}
            <Radar
              name="United States"
              dataKey="US"
              stroke="hsl(var(--us))"
              fill="hsl(var(--us))"
              fillOpacity={0.18}
              strokeWidth={2}
              dot={usDot}
              activeDot={false}
            />
            <Radar
              name="China"
              dataKey="CN"
              stroke="hsl(var(--china))"
              fill="hsl(var(--china))"
              fillOpacity={0.14}
              strokeWidth={2}
              dot={cnDot}
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

        {/* Floating tooltip — positioned relative to chart container, never over centre */}
        {hover && (
          <RadarTooltipBox
            hover={hover}
            containerW={containerSize.w}
            containerH={containerSize.h}
          />
        )}
      </div>

      {/* Confidence dot legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {(['high', 'medium', 'low'] as Confidence[]).map((conf) => {
          const r = DOT_R[conf]
          const opacity = DOT_OPACITY[conf]
          return (
            <div key={conf} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width={r * 2 + 2} height={r * 2 + 2}>
                <circle
                  cx={r + 1} cy={r + 1} r={r}
                  fill="hsl(var(--muted-foreground))"
                  opacity={opacity}
                />
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
