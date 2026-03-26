import type { ScoreCardDimension, Confidence, Leader, RadarDimension, DimensionTab } from './data'

import executiveSummary from '../data/executive_summary.json'
import frontierModelsData from '../data/frontier_models.json'
import talentData from '../data/talent.json'
import computeData from '../data/compute.json'
import adoptionData from '../data/adoption.json'
import diffusionData from '../data/diffusion.json'
import energyData from '../data/energy.json'

// ── Helpers ──────────────────────────────────────────────────────────────────

function mapConfidence(s: string): Confidence {
  const lower = s.toLowerCase()
  if (lower.startsWith('high')) return 'high'
  if (lower.startsWith('medium')) return 'medium'
  return 'low'
}

function mapLeader(winner: string): Leader {
  if (winner === 'US') return 'US'
  if (winner === 'China') return 'CN'
  return 'Tied'
}

function pct(n: number, total: number): number {
  return Math.round((n / total) * 100)
}

function fmt(n: number): string {
  return n.toLocaleString('en-US')
}

const keyToLabel: Record<string, string> = {
  frontier_models: 'Frontier Models',
  talent: 'Talent',
  compute: 'Compute',
  adoption: 'Adoption',
  diffusion: 'Diffusion',
  energy: 'Energy',
}

function getDim(key: string) {
  return executiveSummary.dimensions.find((d) => d.key === key)
}

// ── ScoreCard dimensions ──────────────────────────────────────────────────────
export const scorecardDimensions: ScoreCardDimension[] = executiveSummary.dimensions.map((d) => ({
  id: d.key,
  label: d.label,
  usScore: d.us_score,
  cnScore: d.china_score,
  leader: mapLeader(d.winner),
  delta: d.delta,
  confidence: mapConfidence(d.confidence),
}))

// ── Radar data ────────────────────────────────────────────────────────────────
const { order, us: radarUs, china: radarCn } = executiveSummary.radar_chart_data
export const radarData: RadarDimension[] = order.map((key, i) => ({
  dimension: keyToLabel[key] ?? key,
  US: radarUs[i],
  CN: radarCn[i],
}))

// ── Strategic insights ────────────────────────────────────────────────────────
export const strategicInsights: string[] = executiveSummary.strategic_insights.map(
  (s) => s.bold + s.rest,
)

// ── Per-dimension proxy values ────────────────────────────────────────────────

// Frontier Models
const fmUs = frontierModelsData.summary.US
const fmCn = frontierModelsData.summary.China
const fmTotal = fmUs + fmCn

// Talent
const talUs = talentData.summary.US
const talCn = talentData.summary.China
const talTotal = talUs + talCn

// Compute
const compUsRmax = computeData.summary.US.rmax_pflops
const compCnRmax = computeData.summary.China.rmax_pflops
const compRmaxTotal = compUsRmax + compCnRmax
const compUsSystems = computeData.summary.US.systems
const compCnSystems = computeData.summary.China.systems
const compSystemsTotal = compUsSystems + compCnSystems

// Adoption
const adpUs = adoptionData.summary.US
const adpCn = adoptionData.summary.China

// Diffusion
const difUs = diffusionData.summary.US
const difCn = diffusionData.summary.China

// Energy
const engUs = energyData.summary.US
const engCn = energyData.summary.China

// ── Dimension tabs ────────────────────────────────────────────────────────────
export const dimensionTabs: DimensionTab[] = [
  {
    id: 'frontier_models',
    label: 'Frontier Models',
    headline: `US leads: ${pct(fmUs, fmTotal)}% of tracked model activity`,
    headlineNote: `${fmt(fmUs)} US vs ${fmt(fmCn)} China updates (30 days, HF Hub)`,
    explanation: getDim('frontier_models')?.caveat ?? '',
    barData: [
      { label: 'HF model updates (share %)', US: pct(fmUs, fmTotal), CN: pct(fmCn, fmTotal) },
    ],
    barXLabel: 'Share of combined US + China activity (%)',
    tableRows: [
      { label: '30-day model updates', us: fmt(fmUs), cn: fmt(fmCn) },
      {
        label: 'Score (0–10)',
        us: String(getDim('frontier_models')?.us_score ?? ''),
        cn: String(getDim('frontier_models')?.china_score ?? ''),
      },
    ],
  },
  {
    id: 'talent',
    label: 'Talent',
    headline: `China leads: ${pct(talCn, talTotal)}% of combined AI paper output`,
    headlineNote: `${fmt(talUs)} US vs ${fmt(talCn)} China papers (12 months, OpenAlex)`,
    explanation: getDim('talent')?.caveat ?? '',
    barData: [
      { label: 'AI research papers (share %)', US: pct(talUs, talTotal), CN: pct(talCn, talTotal) },
    ],
    barXLabel: 'Share of combined US + China papers (%)',
    tableRows: [
      { label: '12-month AI papers', us: fmt(talUs), cn: fmt(talCn) },
      {
        label: 'Score (0–10)',
        us: String(getDim('talent')?.us_score ?? ''),
        cn: String(getDim('talent')?.china_score ?? ''),
      },
    ],
  },
  {
    id: 'compute',
    label: 'Compute',
    headline: `US holds ${pct(compUsRmax, compRmaxTotal)}% of combined TOP500 compute power`,
    headlineNote: `${fmt(Math.round(compUsRmax))} vs ${fmt(Math.round(compCnRmax))} PFlops (TOP500, Nov 2025)`,
    explanation: getDim('compute')?.caveat ?? '',
    barData: [
      {
        label: 'TOP500 Rmax capacity (share %)',
        US: pct(compUsRmax, compRmaxTotal),
        CN: pct(compCnRmax, compRmaxTotal),
      },
      {
        label: 'TOP500 system count (share %)',
        US: pct(compUsSystems, compSystemsTotal),
        CN: pct(compCnSystems, compSystemsTotal),
      },
    ],
    barXLabel: 'Share of combined US + China (%)',
    tableRows: [
      { label: 'Rmax performance (PFlops)', us: fmt(Math.round(compUsRmax)), cn: fmt(Math.round(compCnRmax)) },
      { label: 'Systems in TOP500', us: String(compUsSystems), cn: String(compCnSystems) },
      {
        label: 'Score (0–10)',
        us: String(getDim('compute')?.us_score ?? ''),
        cn: String(getDim('compute')?.china_score ?? ''),
      },
    ],
  },
  {
    id: 'adoption',
    label: 'Adoption',
    headline: `China leads on AI adoption: composite ${adpCn.composite_score.toFixed(1)} vs ${adpUs.composite_score.toFixed(1)}`,
    headlineNote: 'enterprise adoption rate + industrial robot density',
    explanation: getDim('adoption')?.caveat ?? '',
    barData: [
      {
        label: 'Enterprise adoption (%)',
        US: Math.round(adpUs.proxies.enterprise_adoption.raw_value),
        CN: Math.round(adpCn.proxies.enterprise_adoption.raw_value),
      },
      {
        label: 'Robot density (normalized 0–100)',
        US: Math.round(adpUs.proxies.robot_density.normalized_score),
        CN: Math.round(adpCn.proxies.robot_density.normalized_score),
      },
      {
        label: 'Composite score (0–100)',
        US: Math.round(adpUs.composite_score),
        CN: Math.round(adpCn.composite_score),
      },
    ],
    barXLabel: 'Score (0–100)',
    tableRows: [
      {
        label: 'Enterprise AI adoption',
        us: `${adpUs.proxies.enterprise_adoption.raw_value}%`,
        cn: `${adpCn.proxies.enterprise_adoption.raw_value}% (est.)`,
      },
      {
        label: 'Robot density',
        us: `${fmt(adpUs.proxies.robot_density.raw_value)} / 10K workers`,
        cn: `${fmt(adpCn.proxies.robot_density.raw_value)} / 10K workers`,
      },
    ],
  },
  {
    id: 'diffusion',
    label: 'Diffusion',
    headline: `US AI accounts for ${Math.round(difUs.composite_score)}% of combined global diffusion footprint`,
    headlineNote: 'HF open-model downloads + cloud platform coverage',
    explanation: getDim('diffusion')?.caveat ?? '',
    barData: [
      {
        label: 'HF model downloads (share %)',
        US: Math.round(difUs.proxies.hf_downloads.share_score),
        CN: Math.round(difCn.proxies.hf_downloads.share_score),
      },
      {
        label: 'Cloud AI footprint (share %)',
        US: Math.round(difUs.proxies.cloud_footprint.share_score),
        CN: Math.round(difCn.proxies.cloud_footprint.share_score),
      },
      {
        label: 'Composite score',
        US: Math.round(difUs.composite_score),
        CN: Math.round(difCn.composite_score),
      },
    ],
    barXLabel: 'Share of combined US + China (%)',
    tableRows: [
      {
        label: 'Monthly HF downloads',
        us: `${(difUs.proxies.hf_downloads.raw_value / 1e6).toFixed(0)}M`,
        cn: `${(difCn.proxies.hf_downloads.raw_value / 1e6).toFixed(0)}M`,
      },
      {
        label: 'Cloud countries reached',
        us: String(difUs.proxies.cloud_footprint.raw_value),
        cn: String(difCn.proxies.cloud_footprint.raw_value),
      },
    ],
  },
  {
    id: 'energy',
    label: 'Energy',
    headline: `China leads on AI energy scaling: composite ${engCn.composite_score.toFixed(1)} vs ${engUs.composite_score.toFixed(1)}`,
    headlineNote: 'capacity addition rate, DC demand headroom, grid connection speed',
    explanation: getDim('energy')?.caveat ?? '',
    barData: [
      {
        label: 'Capacity addition rate (norm.)',
        US: Math.round(engUs.proxies.capacity_addition_rate.normalized_score),
        CN: Math.round(engCn.proxies.capacity_addition_rate.normalized_score),
      },
      {
        label: 'DC demand headroom (norm.)',
        US: Math.round(engUs.proxies.dc_demand_headroom.normalized_score),
        CN: Math.round(engCn.proxies.dc_demand_headroom.normalized_score),
      },
      {
        label: 'Grid connection speed (norm.)',
        US: Math.round(engUs.proxies.grid_connection_speed.normalized_score),
        CN: Math.round(engCn.proxies.grid_connection_speed.normalized_score),
      },
      {
        label: 'Composite score (0–100)',
        US: Math.round(engUs.composite_score),
        CN: Math.round(engCn.composite_score),
      },
    ],
    barXLabel: 'Score (0–100)',
    tableRows: [
      {
        label: 'Annual capacity growth',
        us: `${engUs.proxies.capacity_addition_rate.raw_value.toFixed(1)}%`,
        cn: `${engCn.proxies.capacity_addition_rate.raw_value.toFixed(1)}%`,
      },
      {
        label: 'DC share of grid',
        us: `${engUs.proxies.dc_demand_headroom.raw_value}%`,
        cn: `${engCn.proxies.dc_demand_headroom.raw_value}%`,
      },
      {
        label: 'Grid connection speed',
        us: `${engUs.proxies.grid_connection_speed.raw_value} / 100`,
        cn: `${engCn.proxies.grid_connection_speed.raw_value} / 100`,
      },
    ],
  },
]
