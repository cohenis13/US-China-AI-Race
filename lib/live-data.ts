import type { ScoreCardDimension, Confidence, Leader, RadarDimension, DimensionTab, DimensionSource, StrategicInsight } from './data'

// Fetch from the production static site so we always get the latest pipeline data,
// regardless of which branch this Next.js app is deployed from.
const BASE = 'https://us-china-ai-race.vercel.app/data'

// ── Mojibake fix ──────────────────────────────────────────────────────────────
// The pipeline produces JSON where some strings are Windows-1252 interpretations
// of UTF-8 bytes (e.g. em dash "—" becomes "â€""). We reverse this here.
const WIN1252_TO_BYTE: Record<number, number> = {
  0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85,
  0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A,
  0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
  0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
  0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C,
  0x017E: 0x9E, 0x0178: 0x9F,
}

function decodeMojibake(str: string): string {
  const bytes = new Uint8Array(str.length)
  for (let i = 0; i < str.length; i++) {
    const cp = str.charCodeAt(i)
    // A character outside Latin-1 that isn't a Windows-1252 special char
    // means this isn't a mojibake string — leave it untouched.
    if (cp > 0xFF && WIN1252_TO_BYTE[cp] === undefined) return str
    bytes[i] = WIN1252_TO_BYTE[cp] ?? cp
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return str // bytes don't form valid UTF-8 → wasn't mojibake
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fixStrings(obj: any): any {
  if (typeof obj === 'string') return decodeMojibake(obj)
  if (Array.isArray(obj)) return obj.map(fixStrings)
  if (obj !== null && typeof obj === 'object')
    return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, fixStrings(v)]))
  return obj
}

// Always fetch fresh — data is updated daily by the pipeline
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function fetchJson(file: string): Promise<any> {
  const res = await fetch(`${BASE}/${file}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to fetch ${file}: ${res.status}`)
  return fixStrings(await res.json())
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

interface TopSystem {
  rank: number
  name: string
  country: string
  rmax_pflops: number
}

interface TopModel {
  rank: number
  name: string
  organization: string
  country: string
  publication_date: string
  training_compute_flop: number
}

interface Compute {
  summary: {
    US: {
      training_compute_flop?: number; model_count?: number
      // new shape post-Epoch AI
      top500_systems?: number; top500_rmax_pflops?: number
      // legacy shape (old TOP500-only output)
      systems?: number; rmax_pflops?: number
    }
    China: {
      training_compute_flop?: number; model_count?: number
      top500_systems?: number; top500_rmax_pflops?: number
      systems?: number; rmax_pflops?: number
    }
  }
  epoch_ai?: {
    cutoff_date: string
    top_models_by_compute: TopModel[]
  }
  top500?: {
    list_edition: string
    summary: { US: { systems: number; rmax_pflops: number }; China: { systems: number; rmax_pflops: number } }
    top_systems: TopSystem[]
  }
  list_edition?: string   // legacy
  top_systems?: TopSystem[] // legacy
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

const METHODOLOGY_URL = 'https://us-china-ai-race.vercel.app/docs/methodology.html'

const TAB_SOURCES: Record<string, DimensionSource[]> = {
  frontier_models: [
    { label: 'LMSYS Chatbot Arena', url: 'https://huggingface.co/datasets/mathewhe/chatbot-arena-elo' },
    { label: 'Epoch AI', url: 'https://epoch.ai/data/notable-ai-models' },
  ],
  talent: [
    { label: 'OpenAlex API', url: 'https://api.openalex.org/works' },
  ],
  compute: [
    { label: 'TOP500', url: 'https://www.top500.org' },
    { label: 'Epoch AI — Frontier Data Centers', url: 'https://epoch.ai/data' },
    { label: 'IEA — Energy and AI 2025', url: 'https://www.iea.org/reports/energy-and-ai' },
    { label: 'NVIDIA Geographic Revenue', url: 'http://bullfincher.io/companies/nvidia-corporation/revenue-by-geography' },
  ],
  adoption: [
    { label: 'McKinsey State of AI 2025', url: 'https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai' },
    { label: 'Stanford AI Index 2025', url: 'https://aiindex.stanford.edu/report/' },
    { label: 'IFR World Robotics 2024', url: 'https://ifr.org' },
  ],
  diffusion: [
    { label: 'Hugging Face Hub', url: 'https://huggingface.co' },
    { label: 'AWS', url: 'https://aws.amazon.com/about-aws/global-infrastructure/' },
    { label: 'Azure', url: 'https://azure.microsoft.com/en-us/explore/global-infrastructure/geographies/' },
    { label: 'Google Cloud', url: 'https://cloud.google.com/about/locations' },
  ],
  energy: [
    { label: 'IEA Energy and AI 2025', url: 'https://www.iea.org/reports/energy-and-ai' },
    { label: 'EIA Electric Power Monthly', url: 'https://www.eia.gov/electricity/monthly/' },
    { label: 'LBNL Queued Up 2024', url: 'https://emp.lbl.gov/queues' },
    { label: 'IEA WEO 2024', url: 'https://www.iea.org/reports/world-energy-outlook-2024' },
  ],
}

// ── Main export ───────────────────────────────────────────────────────────────

export interface LiveData {
  scorecardDimensions: ScoreCardDimension[]
  radarData: RadarDimension[]
  strategicInsights: StrategicInsight[]
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
  const dimByKey = Object.fromEntries(exec.dimensions.map((d) => [d.key, d]))
  const radarData: RadarDimension[] = order.map((key, i) => ({
    dimension: keyToLabel[key] ?? key,
    US: radarUs[i],
    CN: radarCn[i],
    confidence: mapConfidence(dimByKey[key]?.confidence ?? ''),
    caveat: dimByKey[key]?.caveat ?? '',
  }))

  // ── Strategic insights ──────────────────────────────────────────────────────
  const strategicInsights = exec.strategic_insights.map((s: { bold: string; rest: string }) => ({
    bold: s.bold,
    rest: s.rest,
  }))

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

  // Epoch AI training compute (primary) — with TOP500 fallback
  const compUsFlop     = comp.summary.US.training_compute_flop
  const compCnFlop     = comp.summary.China.training_compute_flop
  const compUsModels   = comp.summary.US.model_count ?? 0
  const compCnModels   = comp.summary.China.model_count ?? 0
  const epochOk        = compUsFlop != null && compCnFlop != null
  const compFlopTotal  = epochOk ? (compUsFlop! + compCnFlop!) : 1

  // TOP500 (secondary / supplementary)
  const top500Data     = comp.top500 ?? null
  const legacySystems  = comp.top_systems ?? null   // pre-Epoch shape
  const compEdition    = top500Data?.list_edition ?? comp.list_edition ?? 'Nov 2025'
  // Rmax: new nested shape → new flat shape → legacy flat shape → 0
  const compUsRmax    = top500Data?.summary?.US?.rmax_pflops
    ?? comp.summary.US.top500_rmax_pflops
    ?? comp.summary.US.rmax_pflops    // legacy TOP500-only format
    ?? 0
  const compCnRmax    = top500Data?.summary?.China?.rmax_pflops
    ?? comp.summary.China.top500_rmax_pflops
    ?? comp.summary.China.rmax_pflops // legacy
    ?? 0
  const compRmaxTotal  = compUsRmax + compCnRmax
  const compUsSystems = top500Data?.summary?.US?.systems
    ?? comp.summary.US.top500_systems
    ?? comp.summary.US.systems        // legacy
    ?? 0
  const compCnSystems = top500Data?.summary?.China?.systems
    ?? comp.summary.China.top500_systems
    ?? comp.summary.China.systems     // legacy
    ?? 0
  const compSystemsTotal = compUsSystems + compCnSystems

  const topSystems     = top500Data?.top_systems ?? legacySystems ?? []
  const compTopUs      = topSystems.find(s => s.country === 'US')
  const compUsInTop20  = topSystems.filter(s => s.country === 'US').length

  // Top models by training compute from Epoch AI
  const epochTopModels  = comp.epoch_ai?.top_models_by_compute ?? []
  const epochCutoff     = comp.epoch_ai?.cutoff_date ?? '2023-01-01'

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
      sources: TAB_SOURCES.frontier_models,
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
      sources: TAB_SOURCES.talent,
    },
    {
      id: 'compute',
      label: 'Compute',
      headline: epochOk
        ? `US accounts for ${pct(compUsFlop!, compFlopTotal)}% of disclosed AI training compute`
        : `US holds ${pct(compUsRmax, compRmaxTotal)}% of disclosed TOP500 compute`,
      headlineNote: epochOk
        ? `Notable models since ${epochCutoff.slice(0,4)} — US ${compUsModels} models, China ${compCnModels} models (Epoch AI)`
        : `${fmt(Math.round(compUsRmax))} vs ${fmt(Math.round(compCnRmax))} PFlops (TOP500, ${compEdition})`,
      explanation: epochOk
        ? `Epoch AI tracks training compute (FLOPs) for notable AI models globally. Since ${epochCutoff.slice(0,4)}, US labs account for ~${pct(compUsFlop!, compFlopTotal)}% of disclosed training compute vs China's ~${pct(compCnFlop!, compFlopTotal)}%. This understates China's real position: frontier closed models (Qwen-max, Doubao) and Huawei Ascend deployments do not disclose compute. Analyst estimates put the real frontier AI compute gap at roughly 3–5×, not the 6× implied by disclosed figures alone.`
        : getCaveat('compute'),
      barData: epochOk
        ? [
            { label: 'Training compute share — Epoch AI (%)', US: pct(compUsFlop!, compFlopTotal), CN: pct(compCnFlop!, compFlopTotal) },
            { label: 'Notable models since 2023 (share %)',   US: pct(compUsModels, compUsModels + compCnModels), CN: pct(compCnModels, compUsModels + compCnModels) },
            ...(compRmaxTotal > 0 ? [{ label: 'TOP500 Rmax share — disclosed only (%)', US: pct(compUsRmax, compRmaxTotal), CN: pct(compCnRmax, compRmaxTotal) }] : []),
          ]
        : [
            { label: 'TOP500 Rmax capacity share (%)', US: pct(compUsRmax, compRmaxTotal), CN: pct(compCnRmax, compRmaxTotal) },
            { label: 'TOP500 system count share (%)',  US: pct(compUsSystems, compSystemsTotal), CN: pct(compCnSystems, compSystemsTotal) },
          ],
      barXLabel: 'Share of combined US + China (%)',
      tableRows: [
        ...(epochOk ? [
          { label: 'Training compute — notable models', us: `${compUsFlop!.toExponential(2)} FLOPs`, cn: `${compCnFlop!.toExponential(2)} FLOPs` },
          { label: 'Notable models tracked (since 2023)', us: String(compUsModels), cn: String(compCnModels) },
          ...(epochTopModels.length > 0 ? [{ label: '#1 model by compute', us: epochTopModels[0]?.country === 'US' ? epochTopModels[0].name : '—', cn: epochTopModels.find(m => m.country === 'China')?.name ?? '—' }] : []),
        ] : []),
        ...(compRmaxTotal > 0 ? [
          { label: `TOP500 Rmax — ${compEdition} (supplementary)`, us: `${fmt(Math.round(compUsRmax))} PFlops`, cn: `${fmt(Math.round(compCnRmax))} PFlops` },
          { label: 'TOP500 systems', us: String(compUsSystems), cn: `${compCnSystems} (non-disclosure from 2023)` },
          { label: `TOP500 #1 system (US)`, us: compTopUs ? `${compTopUs.name} — ${fmt(Math.round(compTopUs.rmax_pflops))} PFlops` : '—', cn: `None in top ${topSystems.length}` },
        ] : []),
        { label: 'NVIDIA revenue share (est.)', us: '~47%', cn: '~13%' },
        { label: 'Score (0–10)', ...getScore('compute') },
      ],
      sources: TAB_SOURCES.compute,
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
        { label: 'Score (0–10)', ...getScore('adoption') },
      ],
      sources: TAB_SOURCES.adoption,
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
        { label: 'Score (0–10)', ...getScore('diffusion') },
      ],
      sources: TAB_SOURCES.diffusion,
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
        { label: 'Score (0–10)', ...getScore('energy') },
      ],
      sources: TAB_SOURCES.energy,
    },
  ]

  return { scorecardDimensions, radarData, strategicInsights, dimensionTabs }
}
