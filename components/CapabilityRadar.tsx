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

const CHART_H       = 300
const HIT_THRESHOLD = 22   // px — cursor must be within this radius to activate a dot

// ── Types ─────────────────────────────────────────────────────────────────────
interface DotPos {
  svgX: number; svgY: number
  dimension: string; value: number
  country: 'US' | 'CN'; confidence: Confidence; caveat: string
}

interface HoverState extends DotPos {
  mouseX: number; mouseY: number
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function RadarTooltipBox({ hover, containerW }: { hover: HoverState; containerW: number }) {
  const W      = 240
  const OFFSET = 14

  // Flip to the opposite quadrant from the cursor so the tooltip
  // never covers the chart centre or the hovered dot.
  let left: number | undefined
  let right: number | undefined
  let top: number | undefined
  let bottom: number | undefined

  if (hover.mouseX > containerW / 2) {
    right = Math.max(containerW - hover.mouseX + OFFSET, 4)
  } else {
    left = Math.min(hover.mouseX + OFFSET, containerW - W - 4)
  }
  if (hover.mouseY > CHART_H / 2) {
    bottom = Math.max(CHART_H - hover.mouseY + OFFSET, 4)
  } else {
    top = hover.mouseY + OFFSET
  }

  const color = hover.country === 'US' ? 'hsl(var(--us))' : 'hsl(var(--china))'
  const label = hover.country === 'US' ? 'United States' : 'China'

  return (
    <div style={{
      position: 'absolute', left, right, top, bottom, width: W,
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
        <span style={{ color, fontWeight: 600 }}>{label}:</span>
        {' '}{Number(hover.value).toFixed(1)} / 10
      </div>
      <div style={{
        color: 'hsl(var(--muted-foreground))', fontWeight: 500,
        marginBottom: hover.caveat ? 5 : 0,
      }}>
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

  // Dot positions are registered by the purely-visual dot renderers during
  // Recharts' own render pass. No events live on SVG elements — all hover
  // detection is via onMouseMove on the container div, which is crash-safe.
  const dotPositions = useRef<DotPos[]>([])

  const registerDot = useCallback((pos: DotPos) => {
    const idx = dotPositions.current.findIndex(
      p => p.dimension === pos.dimension && p.country === pos.country
    )
    if (idx >= 0) dotPositions.current[idx] = pos
    else dotPositions.current.push(pos)
  }, [])

  // ── Purely visual dot renderers (zero event handlers) ────────────────────
  // useMemo keeps them stable so Recharts never remounts the dot elements.
  const usDot = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return function USDot(props: any): any {
      const { cx, cy, payload } = props
      if (cx == null || cy == null || !payload) return null
      const conf = (payload.confidence ?? 'low') as Confidence
      registerDot({
        svgX: cx, svgY: cy,
        dimension: payload.dimension,
        value: payload.US,
        country: 'US', confidence: conf, caveat: payload.caveat ?? '',
      })
      return (
        <circle
          cx={cx} cy={cy}
          r={DOT_R[conf]}
          fill="hsl(var(--us))"
          opacity={DOT_OPACITY[conf]}
          style={{ pointerEvents: 'none' }}
        />
      )
    }
  }, [registerDot])

  const cnDot = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return function CNDot(props: any): any {
      const { cx, cy, payload } = props
      if (cx == null || cy == null || !payload) return null
      const conf = (payload.confidence ?? 'low') as Confidence
      registerDot({
        svgX: cx, svgY: cy,
        dimension: payload.dimension,
        value: payload.CN,
        country: 'CN', confidence: conf, caveat: payload.caveat ?? '',
      })
      return (
        <circle
          cx={cx} cy={cy}
          r={DOT_R[conf]}
          fill="hsl(var(--china))"
          opacity={DOT_OPACITY[conf]}
          style={{ pointerEvents: 'none' }}
        />
      )
    }
  }, [registerDot])

  // ── Mouse handling on container div ──────────────────────────────────────
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return

    // SVG coordinate origin = top-left of the container div
    // (ResponsiveContainer fills the div exactly)
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top

    let nearest: DotPos | null = null
    let minDist = Infinity

    for (const pos of dotPositions.current) {
      const dist = Math.hypot(mouseX - pos.svgX, mouseY - pos.svgY)
      if (dist < minDist && dist < HIT_THRESHOLD) {
        minDist = dist
        nearest = pos
      }
    }

    setHover(nearest ? { ...nearest, mouseX, mouseY } : null)
  }, [])

  const handleMouseLeave = useCallback(() => setHover(null), [])

  const containerW = containerRef.current?.offsetWidth ?? 400

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Scores 0–10 across six strategic dimensions
        </p>
      </div>

      {/* position:relative anchors the absolutely-positioned tooltip */}
      <div
        ref={containerRef}
        style={{ position: 'relative' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <ResponsiveContainer width="100%" height={CHART_H}>
          <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
            <PolarGrid
              stroke="hsl(var(--border))"
              strokeDasharray="3 3"
              strokeWidth={0.8}
            />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{
                fill: 'hsl(var(--muted-foreground))',
                fontSize: 11,
                fontFamily: 'var(--font-inter)',
              }}
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
                <span style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>
                  {value}
                </span>
              )}
            />
          </RadarChart>
        </ResponsiveContainer>

        {hover && (
          <RadarTooltipBox hover={hover} containerW={containerW} />
        )}
      </div>

      {/* Confidence legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {(['high', 'medium', 'low'] as Confidence[]).map((conf) => {
          const r = DOT_R[conf]
          return (
            <div key={conf} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width={r * 2 + 2} height={r * 2 + 2}>
                <circle
                  cx={r + 1} cy={r + 1} r={r}
                  fill="hsl(var(--muted-foreground))"
                  opacity={DOT_OPACITY[conf]}
                />
              </svg>
              <span style={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}>
                {CONF_LABEL[conf]}
              </span>
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
