'use client'

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from 'recharts'
import type { RadarDimension, Confidence } from '@/lib/data'

// Dot radius by confidence level
const DOT_R: Record<Confidence, number> = { high: 7, medium: 4.5, low: 3 }
const DOT_OPACITY: Record<Confidence, number> = { high: 1, medium: 0.75, low: 0.5 }

// Custom dot renderer — size varies by confidence
function ConfidenceDot(props: {
  cx?: number; cy?: number; payload?: RadarDimension; fill?: string
}) {
  const { cx, cy, payload, fill } = props
  if (cx == null || cy == null || !payload) return null
  const conf: Confidence = payload.confidence ?? 'low'
  const r = DOT_R[conf]
  const opacity = DOT_OPACITY[conf]
  return <circle cx={cx} cy={cy} r={r} fill={fill} opacity={opacity} stroke="none" />
}

// Custom tooltip
function RadarTooltip({ active, payload }: {
  active?: boolean
  payload?: Array<{ payload: RadarDimension }>
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as RadarDimension
  const conf = d.confidence ?? 'low'
  const confLabel: Record<Confidence, string> = {
    high: 'High confidence',
    medium: 'Medium confidence',
    low: 'Lower confidence',
  }
  const confColor: Record<Confidence, string> = {
    high:   'hsl(var(--us))',
    medium: 'hsl(var(--muted-foreground))',
    low:    'hsl(var(--china))',
  }
  return (
    <div style={{
      background: 'hsl(var(--card))',
      border: '1px solid hsl(var(--border))',
      borderRadius: 8,
      padding: '10px 14px',
      maxWidth: 280,
      fontSize: 12,
      lineHeight: 1.5,
      color: 'hsl(var(--foreground))',
      boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{d.dimension}</div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 6 }}>
        <span>
          <span style={{ color: 'hsl(var(--us))', fontWeight: 600 }}>US </span>
          {d.US.toFixed(1)}
        </span>
        <span>
          <span style={{ color: 'hsl(var(--china))', fontWeight: 600 }}>CN </span>
          {d.CN.toFixed(1)}
        </span>
      </div>
      <div style={{ color: confColor[conf], fontWeight: 500, marginBottom: d.caveat ? 6 : 0 }}>
        {confLabel[conf]}
      </div>
      {d.caveat && (
        <div style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11, lineHeight: 1.4 }}>
          {d.caveat}
        </div>
      )}
    </div>
  )
}

export default function CapabilityRadar({ data }: { data: RadarDimension[] }) {
  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
      <div className="mb-1">
        <h2 className="text-sm font-semibold text-foreground">Capability Overview</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Scores 0–10 across six strategic dimensions</p>
      </div>

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
          <Tooltip content={<RadarTooltip />} />
          <Radar
            name="United States"
            dataKey="US"
            stroke="hsl(var(--us))"
            fill="hsl(var(--us))"
            fillOpacity={0.18}
            strokeWidth={2}
            dot={(props) => (
              <ConfidenceDot
                cx={(props as { cx?: number }).cx}
                cy={(props as { cy?: number }).cy}
                payload={(props as { payload?: RadarDimension }).payload}
                fill="hsl(var(--us))"
              />
            )}
          />
          <Radar
            name="China"
            dataKey="CN"
            stroke="hsl(var(--china))"
            fill="hsl(var(--china))"
            fillOpacity={0.14}
            strokeWidth={2}
            dot={(props) => (
              <ConfidenceDot
                cx={(props as { cx?: number }).cx}
                cy={(props as { cy?: number }).cy}
                payload={(props as { payload?: RadarDimension }).payload}
                fill="hsl(var(--china))"
              />
            )}
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

      {/* Confidence dot legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
        {(['high', 'medium', 'low'] as Confidence[]).map((conf) => {
          const label: Record<Confidence, string> = {
            high: 'High confidence',
            medium: 'Medium confidence',
            low: 'Lower confidence',
          }
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
              <span style={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}>{label[conf]}</span>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
        Scores represent analyst consensus estimates. Higher = stronger relative position.
        Hover a dot to see the data source and caveats.
      </p>
    </div>
  )
}
