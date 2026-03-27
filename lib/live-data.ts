import type { ScoreCardDimension, Confidence, Leader, RadarDimension, DimensionTab } from './data'

// Fetch from the production static site so we always get the latest pipeline data,
// regardless of which branch this Next.js app is deployed from.
const BASE = 'https://us-china-ai-race.vercel.app/data'

// Always fetch fresh — data is updated daily by the pipeline
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function fetchJson(file: string): Promise<any> {
  const res = await fetch(`${BASE}/${file}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch ${file}: ${res.status}`)
  return res.json()
}

// ── Minimal types for the JSON shapes we consume ─────────────────────────────

interface ExecDimension {
  key: string
  label: string
  us_score: number
  china_score: number
  winner: string
  delta: number
  confidence: string
  caveat: string
}

interface ExecutiveSummary {
  dimensions: ExecDimension[]
  strategic_insights: { bold: string; rest: string }[]
  radar_chart_data: { order: string[]; us: number[]; china: number[] }
}

interface FrontierProxy {
  raw_value: number
  share_score: number
}
interface FrontierCountry {
  composite_score: number
  proxies: {
    capability: FrontierProxy
    output:     FrontierProxy
  }
}
interface FrontierLeaderboardModel {
  rank: number
  model: string
  developer: string
  country: string
  elo: number | null
}
interface FrontierModels {
  summary: { US: FrontierCountry; China: FrontierCountry }
  leaderboard: {
    models: FrontierLeaderboardModel[]
    us_count: number
    china_count: number
  }
}

interface TalentCountry {
  composite_score: number
  proxies: {
    paper_volume:   { raw_value: number; share_score: number }
    top_conference: { raw_value: number; share_score: number }
    high_impact:    { raw_value: number; share_score: number }
  }
}
interface Talent {
  summary: { US: TalentCountry; China: TalentCountry }
}

interface Compute {
  summary: {
    US: { systems: number; rmax_pflops: number }
    China: { systems: number; rmax_pflops: number }
  }
}

interface AdoptionProxy {
  composite_score: number
  proxies: {
    enterprise_adoption: { raw_value: number }
    robot_density: { raw_value: number; normalized_score: number }
  }
}

interface Adoption {
  summary: { US: AdoptionProxy; China: AdoptionProxy }
}

interface DiffusionProxy {
  composite_score: number
  proxies: {
    hf_downloads: { raw_value: number; share_score: number }
    cloud_footprint: { raw_value: number; share_score: number }
  }
}

interface Diffusion {
  summary: { US: DiffusionProxy; China: DiffusionProxy }
}

interface EnergyProxy {
  composite_score: number
  proxies: {
    capacity_addition_rate: { raw_value: number; normalized_score: number }
    dc_demand_headroom: { raw_value: number; normalized_score: number }
    grid_connection_speed: { raw_value: number; normalized_score: number }
  }
}

interface Energy {
  summary: { US: EnergyProxy; China: EnergyProxy }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Main export ───────────────────────────────────────────────────────────────

export interface LiveData {
  scorecardDimensions: ScoreCardDimension[]
  radarData: RadarDimension[]
  strategicInsights: string[]
  dimensionTabs: DimensionTab[]
}

export async function getLiveData(): Promise<LiveData> {
  const [exec, fm, tal, comp, adp, dif, eng]: [
    ExecutiveSummary, FrontierModels, Talent, Compute, Adoption, Diffusion, Energy
  ] = await Promise.all([
    fetchJson('executive_summary.json'),
    fetchJson('frontier_models.json'),
    fetchJson('talent.json'),
    fetchJson('compute.json'),
    fetchJson('adoption.json'),
    fetchJson('diffusion.json'),
    fetchJson('energy.json'),
  ])

  // ── ScoreCard ───────────────────────────────────────────────────────────────
  const scorecardDimensions: ScoreCardDimension[] = exec.dimensions.map((d) => ({
    id: d.key,
    label: d.label,
    usScore: d.us_score,
    cnScore: d.china_score,
    leader: mapLeader(d.winner),
    delta: d.delta,
    confidence: mapConfidence(d.confidence),
  }))

  // ── Radar ───────────────────────────────────────────────────────────────────
  const { order, us: radarUs, china: radarCn } = exec.radar_chart_data
  const radarData: RadarDimension[] = order.map((key, i) => ({
    dimension: keyToLabel[key] ?? key,
    US: radarUs[i],
    CN: radarCn[i],
  }))

  // ── Strategic insights ──────────────────────────────────────────────────────
  const strategicInsights: string[] = exec.strategic_insights.map((s) => s.bold + s.rest)

  // ── Per-dimension proxy shortcuts ───────────────────────────────────────────
  const fmUs         = fm.summary.US
  const fmCn         = fm.summary.China
  const fmUsComp     = fmUs.composite_score
  const fmCnComp     = fmCn.composite_score
  const fmLeader     = fmUsComp >= fmCnComp ? 'US' : 'China'
  const fmCapUsCount = fmUs.proxies.capability.raw_value
  const fmCapCnCount = fmCn.proxies.capability.raw_value
  const fmCapUsShare = fmUs.proxies.capability.share_score
  const fmCapCnShare = fmCn.proxies.capability.share_score
  const fmOutUsCount = fmUs.proxies.output.raw_value
  const fmOutCnCount = fmCn.proxies.output.raw_value
  const fmOutUsShare = fmUs.proxies.output.share_score
  const fmOutCnShare = fmCn.proxies.output.share_score

  const talUs = tal.summary.US
  const talCn = tal.summary.China
  const talUsComposite = talUs.composite_score
  const talCnComposite = talCn.composite_score
  const talLeader = talUsComposite >= talCnComposite ? 'US' : 'China'
  const talVolUsShare  = talUs.proxies.paper_volume.share_score
  const talVolCnShare  = talCn.proxies.paper_volume.share_score
  const talConfUsShare = talUs.proxies.top_conference.share_score
  const talConfCnShare = talCn.proxies.top_conference.share_score
  const talImpUsShare  = talUs.proxies.high_impact.share_score
  const talImpCnShare  = talCn.proxies.high_impact.share_score
  const talVolUsRaw    = talUs.proxies.paper_volume.raw_value
  const talVolCnRaw    = talCn.proxies.paper_volume.raw_value
  const talConfUsRaw   = talUs.proxies.top_conference.raw_value
  const talConfCnRaw   = talCn.proxies.top_conference.raw_value
  const talImpUsRaw    = talUs.proxies.high_impact.raw_value
  const talImpCnRaw    = talCn.proxies.high_impact.raw_value

  const compUsRmax = comp.summary.US.rmax_pflops
  const compCnRmax = comp.summary.China.rmax_pflops
  const compRmaxTotal = compUsRmax + compCnRmax
  const compUsSystems = comp.summary.US.systems
  const compCnSystems = comp.summary.China.systems
  const compSystemsTotal = compUsSystems + compCnSystems

  const adpUs = adp.summary.US
  const adpCn = adp.summary.China

  const difUs = dif.summary.US
  const difCn = dif.summary.China

  const engUs = eng.summary.US
  const engCn = eng.summary.China

  function getCaveat(key: string): string {
    return exec.dimensions.find((d) => d.key === key)?.caveat ?? ''
  }

  function getScore(key: string): { us: string; cn: string } {
    const d = exec.dimensions.find((dim) => dim.key === key)
    return { us: String(d?.us_score ?? ''), cn: String(d?.china_score ?? '') }
  }

  // ── Dimension tabs ──────────────────────────────────────────────────────────
  const dimensionTabs: DimensionTab[] = [
    {
      id: 'frontier_models',
      label: 'Frontier Models',
      headline: fmLeader === 'US'
        ? `US leads on frontier model composite: ${fmUsComp.toFixed(1)} vs ${fmCnComp.toFixed(1)}`
        : `China leads on frontier model composite: ${fmCnComp.toFixed(1)} vs ${fmUsComp.toFixed(1)}`,
      headlineNote: 'Arena Elo capability ranking (60%) + Epoch AI notable model output (40%)',
      explanation: getCaveat('frontier_models'),
      barData: [
        { label: 'Capability share — top 20 Arena Elo (%)', US: Math.round(fmCapUsShare), CN: Math.round(fmCapCnShare) },
        { label: 'Output share — notable models 2y (%)',    US: Math.round(fmOutUsShare), CN: Math.round(fmOutCnShare) },
        { label: 'Composite score',                         US: Math.round(fmUsComp),     CN: Math.round(fmCnComp)     },
      ],
      barXLabel: 'Share of combined US + China (%)',
      tableRows: [
        { label: 'Models in top 20 (Arena Elo)',        us: fmt(fmCapUsCount), cn: fmt(fmCapCnCount) },
        { label: 'Notable models released (2y, Epoch)', us: fmt(fmOutUsCount), cn: fmt(fmOutCnCount) },
        { label: 'Score (0–10)', ...getScore('frontier_models') },
      ],
    },
    {
      id: 'talent',
      label: 'Talent',
      headline: talLeader === 'US'
        ? `US leads on talent composite: ${talUsComposite.toFixed(1)} vs ${talCnComposite.toFixed(1)}`
        : `China leads on talent composite: ${talCnComposite.toFixed(1)} vs ${talUsComposite.toFixed(1)}`,
      headlineNote: 'paper volume (30%) + quality papers cited ≥25 (40%) + high-impact cited ≥100 (30%)',
      explanation: getCaveat('talent'),
      barData: [
        { label: 'Paper volume share (%)',            US: Math.round(talVolUsShare),  CN: Math.round(talVolCnShare)  },
        { label: 'Quality papers share (cited ≥25%)', US: Math.round(talConfUsShare), CN: Math.round(talConfCnShare) },
        { label: 'High-impact papers share (%)',     US: Math.round(talImpUsShare),  CN: Math.round(talImpCnShare)  },
        { label: 'Composite score',                  US: Math.round(talUsComposite), CN: Math.round(talCnComposite) },
      ],
      barXLabel: 'Share of combined US + China (%)',
      tableRows: [
        { label: 'AI papers (12-month)',              us: fmt(talVolUsRaw),  cn: fmt(talVolCnRaw)  },
        { label: 'Quality papers cited ≥25 (2y)',       us: fmt(talConfUsRaw), cn: fmt(talConfCnRaw) },
        { label: 'High-impact papers cited ≥100 (3y)', us: fmt(talImpUsRaw),  cn: fmt(talImpCnRaw)  },
        { label: 'Score (0–10)', ...getScore('talent') },
      ],
    },
    {
      id: 'compute',
      label: 'Compute',
      headline: `US holds ${pct(compUsRmax, compRmaxTotal)}% of combined TOP500 compute power`,
      headlineNote: `${fmt(Math.round(compUsRmax))} vs ${fmt(Math.round(compCnRmax))} PFlops (TOP500, Nov 2025)`,
      explanation: getCaveat('compute'),
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
        { label: 'Score (0–10)', ...getScore('compute') },
      ],
    },
    {
      id: 'adoption',
      label: 'Adoption',
      headline: `China leads on AI adoption: composite ${adpCn.composite_score.toFixed(1)} vs ${adpUs.composite_score.toFixed(1)}`,
      headlineNote: 'enterprise adoption rate + industrial robot density',
      explanation: getCaveat('adoption'),
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
      explanation: getCaveat('diffusion'),
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
      explanation: getCaveat('energy'),
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

  return { scorecardDimensions, radarData, strategicInsights, dimensionTabs }
}
