'use client'

import React, { useState, useRef, useCallback, useMemo } from 'react'
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
const DOT_R: Record<Confidence, number>       = { high: 7, medium: 4.5, low: 3 }
const DOT_OPACITY: Record<Confidence, number> = { high: 1, medium: 0.75, low: 0.5 }
const CONF_LABEL: Record<Confidence, string>  = {
  high:   'High confidence',
  medium: 'Medium confidence',
  low:    'Lower confidence',
}

// ── Hover state ───────────────────────────────────────────────────────────────
interface DotInfo {
  dimension: string
  value: number
  country: 'US' | 'CN'
  confidence: Confidence
  caveat: string
}
interface HoverState extends DotInfo {
  /** Mouse position relative to the chart wrapper div */
  x: number
  y: number
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function RadarTooltipBox({ hover, containerW, containerH }: {
  hover: HoverState; containerW: number; containerH: number
}) {
  const TOOLTIP_W = 240
  const OFFSET    = 14

  // Flip left↔right and top↔bottom based on which quadrant the cursor is in,
  // so the tooltip is always away from the chart centre.
  let left:   number | undefined
  let right:  number | undefined
  let top:    number | undefined
  let bottom: number | undefined

  if (hover.x > containerW / 2) {
    right = Math.max(containerW - hover.x + OFFSET, 4)
  } else {
    left = Math.min(hover.x + OFFSET, containerW - TOOLTIP_W - 4)
  }
  if (hover.y > containerH / 2) {
    bottom = Math.max(containerH - hover.y + OFFSET, 4)
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
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 12,
      lineHeight: 1.5,
      color: 'hsl(var(--foreground))',
      boxShadow: '0 4px 16px rgba(0,0,0,0.14)',
      pointerEvents: 'none',
      zIndex: 50,
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

// ── Main component ────────────────────────────────────────────────────────────
export default function CapabilityRadar({ data }: { data: RadarDimension[] }) {
  const [hover, setHover] = useState<HoverState | null>(null)
  const containerRef      = useRef<HTMLDivElement>(null)
  const mousePos          = useRef({ x: 0, y: 0 })
  const containerSize     = useRef({ w: 400, h: 300 })

  // Track cursor position continuously on the wrapper div.
  // Reading position here (not from SVG events) is more reliable.
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    mousePos.current      = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    containerSize.current = { w: rect.width, h: rect.height }
  }, [])

  const handleMouseLeave = useCallback(() => setHover(null), [])

  // Called by a dot when the cursor enters it. Uses mousePos ref (set by
  // onMouseMove above) so we never depend on SVG element event coordinates.
  const handleDotEnter = useCallback((info: DotInfo) => {
    setHover({ ...info, x: mousePos.current.x, y: mousePos.current.y })
  }, [])

  // ── Stable dot renderers (useMemo with [] deps so references never change) ──
  // IMPORTANT: these must be stable. If they changed on every render, Recharts
  // would unmount+remount the dot elements, firing onMouseLeave immediately after
  // onMouseEnter and causing an infinite crash loop.
  const usDot = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return function USDot(props: Record<string, unknown>): any {
      const cx      = props.cx as number | undefined
      const cy      = props.cy as number | undefined
      const payload = props.payload as RadarDimension | undefined
      if (cx == null || cy == null || !payload) return <g />

      const conf    = payload.confidence ?? 'low'
      const r       = DOT_R[conf]
      const opacity = DOT_OPACITY[conf]

      return (
        <g>
          <circle cx={cx} cy={cy} r={r} fill="hsl(var(--us))" opacity={opacity} stroke="none" />
          <circle
            cx={cx} cy={cy} r={Math.max(r + 8, 12)}
            fill="rgba(0,0,0,0)"
            style={{ cursor: 'pointer' }}
            onMouseEnter={(e) => { e.stopPropagation(); handleDotEnter({ dimension: payload.dimension, value: payload.US, country: 'US', confidence: conf, caveat: payload.caveat ?? '' }) }}
            onMouseLeave={(e) => { e.stopPropagation(); setHover(null) }}
          />
        </g>
      )
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // stable: handleDotEnter captured via ref-like callback, setHover is stable

  const cnDot = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return function CNDot(props: Record<string, unknown>): any {
      const cx      = props.cx as number | undefined
      const cy      = props.cy as number | undefined
      const payload = props.payload as RadarDimension | undefined
      if (cx == null || cy == null || !payload) return <g />

      const conf    = payload.confidence ?? 'low'
      const r       = DOT_R[conf]
      const opacity = DOT_OPACITY[conf]

      return (
        <g>
          <circle cx={cx} cy={cy} r={r} fill="hsl(var(--china))" opacity={opacity} stroke="none" />
          <circle
            cx={cx} cy={cy} r={Math.max(r + 8, 12)}
            fill="rgba(0,0,0,0)"
            style={{ cursor: 'pointer' }}
            onMouseEnter={(e) => { e.stopPropagation(); handleDotEnter({ dimension: payload.dimension, value: payload.CN, country: 'CN', confidence: conf, caveat: payload.caveat ?? '' }) }}
            onMouseLeave={(e) => { e.stopPropagation(); setHover(null) }}
          />
        </g>
      )
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Scores 0–10 across six strategic dimensions</p>
      </div>

      {/* position:relative so the tooltip can be absolute-positioned inside */}
      <div
        ref={containerRef}
        style={{ position: 'relative' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
            <PolarGrid stroke="hsl(var(--border))" strokeDasharray="3 3" strokeWidth={0.8} />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11, fontFamily: 'var(--font-inter)' }}
              tickLine={false}
            />
            <Radar
              name="United States"
              dataKey="US"
              stroke="hsl(var(--us))"
              fill="hsl(var(--us))"
              fillOpacity={0.18}
              strokeWidth={2}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              dot={usDot as any}
              activeDot={false}
            />
            <Radar
              name="China"
              dataKey="CN"
              stroke="hsl(var(--china))"
              fill="hsl(var(--china))"
              fillOpacity={0.14}
              strokeWidth={2}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              dot={cnDot as any}
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

        {hover && (
          <RadarTooltipBox
            hover={hover}
            containerW={containerSize.current.w}
            containerH={containerSize.current.h}
          />
        )}
      </div>

      {/* Confidence dot legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {(['high', 'medium', 'low'] as Confidence[]).map((conf) => {
          const r = DOT_R[conf]
          return (
            <div key={conf} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width={r * 2 + 2} height={r * 2 + 2}>
                <circle cx={r + 1} cy={r + 1} r={r} fill="hsl(var(--muted-foreground))" opacity={DOT_OPACITY[conf]} />
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
