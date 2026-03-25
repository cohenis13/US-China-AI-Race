'use client'

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { RadarDimension } from '@/lib/data'

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
          <Radar
            name="United States"
            dataKey="US"
            stroke="hsl(var(--us))"
            fill="hsl(var(--us))"
            fillOpacity={0.18}
            strokeWidth={2}
            dot={{ r: 3, fill: 'hsl(var(--us))', strokeWidth: 0 }}
          />
          <Radar
            name="China"
            dataKey="CN"
            stroke="hsl(var(--china))"
            fill="hsl(var(--china))"
            fillOpacity={0.14}
            strokeWidth={2}
            dot={{ r: 3, fill: 'hsl(var(--china))', strokeWidth: 0 }}
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

      <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
        Scores represent analyst consensus estimates. Higher = stronger relative position.
      </p>
    </div>
  )
}
