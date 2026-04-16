import type { ScoreCardDimension, Confidence, Leader, RadarDimension, DimensionTab, DimensionSource, StrategicInsight, Trend } from './data'

// DATA_BASE overrides the default V1 data source — set it in .env.local for local
// development with local data files, or in Vercel env vars for staging isolation.
// Defaults to V1 production URL so V2 continues working without any config.
const BASE = process.env.DATA_BASE ?? 'https://us-china-ai-race.vercel.app/data'

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
  current_read?: string
}

interface FrontierProxy {
  raw_value: number
  share_score: number
  source_note?: string
  coverage_note?: string
}
interface FrontierReleaseActivity extends FrontierProxy {
  hf_count?: number
  supplement_count?: number
}
interface FrontierBenchmark extends FrontierProxy {
  arena_in_top20?: number
  arena_share_score?: number
  epoch_notable_count?: number
  epoch_share_score?: number
}
interface FrontierEcosystem extends FrontierProxy {
  hf_share?: number
  modelscope_share?: number
}
interface FrontierCountry {
  composite_score: number
  proxies: {
    // v2.0 schema (3 proxies)
    release_activity?:     FrontierReleaseActivity
    benchmark_performance?: FrontierBenchmark
    ecosystem_breadth?:    FrontierEcosystem
    // v1.x schema (2 proxies — backward compat)
    capability?: FrontierProxy
    output?:     FrontierProxy
  }
}
interface FrontierLeaderboardModel {
  rank?: number
  model?: string
  developer: string
  country: string
  elo?: number | null
  notes?: string
}
interface FrontierModels {
  schema_version?: string
  coverage_note?: string
  summary: { US: FrontierCountry; China: FrontierCountry }
  leaderboard?: {
    models?: FrontierLeaderboardModel[]
    us_count?: number
    china_count?: number
  }
  hf_activity?: { US: number; China: number }
}

interface TalentResearchProxy {
  weight: number
  share_score: number
  paper_volume:  { raw_value: number; share_score: number; window: string }
  high_impact:   { raw_value: number; share_score: number; data_ok: boolean }
  top_cited:     { raw_value: number; share_score: number; data_ok: boolean }
}
interface TalentPipelineProxy {
  weight: number
  share_score: number
  phd_annual: number
  source: string
  confidence: string
  coverage_note?: string
}
interface TalentEliteProxy {
  weight: number
  share_score: number
  researcher_count_est?: number
  source: string
  confidence: string
  migration_note?: string
}
interface TalentCountry {
  composite_score: number
  proxies: {
    research_output?: TalentResearchProxy
    pipeline?:        TalentPipelineProxy
    elite_migration?: TalentEliteProxy
    // v1.x legacy proxies (backward compat)
    paper_volume?:   { raw_value: number; share_score: number }
    top_conference?: { raw_value: number; share_score: number }
    high_impact?:    { raw_value: number; share_score: number }
  }
}
interface Talent {
  schema_version?: string
  summary: { US: TalentCountry; China: TalentCountry }
  openalex?: {
    volume:      { us: number; china: number }
    high_impact: { us: number; china: number; data_ok: boolean }
    top_cited:   { us: number; china: number; data_ok: boolean }
  }
  coverage_warning?: string
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

interface ComputeProxy {
  weight: number
  share_score: number
  coverage_note?: string
  source?: string
  confidence?: string
}
interface ComputeTrainingProxy extends ComputeProxy {
  raw_flop?: number | null
  model_count?: number
}
interface ComputeHardwareProxy extends ComputeProxy {
  nvidia_revenue_usd_b?: number | null
  ascend_equivalent_usd_b?: number | null
}
interface ComputeHpcProxy extends ComputeProxy {
  top500_rmax_pflops?: number
  private_cluster_addition_pflops?: number
  non_top500_correction_pflops?: number
  adjusted_pflops?: number
}
interface ComputeCountryV2 {
  composite_score: number
  proxies: {
    training_compute?: ComputeTrainingProxy
    hardware_supply?:  ComputeHardwareProxy
    visible_hpc?:      ComputeHpcProxy
  }
}
interface ComputeHiddenBand {
  china_lower_pct: number
  china_point_pct: number
  china_upper_pct: number
  us_lower_pct: number
  us_point_pct: number
  us_upper_pct: number
  narrative?: string
}

interface Compute {
  schema_version?: string
  summary: {
    // v2.0 schema
    US: ComputeCountryV2 | {
      training_compute_flop?: number; model_count?: number
      top500_systems?: number; top500_rmax_pflops?: number
      systems?: number; rmax_pflops?: number
    }
    China: ComputeCountryV2 | {
      training_compute_flop?: number; model_count?: number
      top500_systems?: number; top500_rmax_pflops?: number
      systems?: number; rmax_pflops?: number
    }
  }
  hidden_compute_band?: ComputeHiddenBand
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

interface InvestmentCountry {
  composite_score: number
  private_investment_usd_b: number
  hyperscaler_capex_usd_b: number
}

interface InvestmentSeries {
  year: number
  us_usd_b: number
  china_usd_b: number
  us_share: number
  source: string
}

interface Investment {
  fetched_at: string
  summary: { US: InvestmentCountry; China: InvestmentCountry }
  private_investment: {
    latest_year: number
    us_usd_b: number
    china_usd_b: number
    us_share: number
    china_share: number
    series: InvestmentSeries[]
  }
  hyperscaler_capex: {
    us_firms: { ticker: string; capex_usd_b: number; period_end: string; source: string }[]
    china_firms: { ticker: string; capex_usd_b: number; period_end: string; source: string }[]
    us_total_usd_b: number
    china_total_usd_b: number
  }
  gov_rd: {
    us: { latest_fy: number; total_ai_usd_b: number }
    china: { estimate_usd_b: number; range_usd_b: [number, number] }
  }
}

interface HistoryEntry {
  date: string
  scores: Record<string, { us: number; china: number }>
}

interface History {
  updated_at: string
  entries: HistoryEntry[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function computeTrend(key: string, currentUs: number, history: History | null): Trend | undefined {
  if (!history?.entries?.length) return undefined
  const entries = [...history.entries].sort((a, b) => a.date.localeCompare(b.date))
  // Find the entry closest to 30 days ago
  const today = new Date()
  const target = new Date(today)
  target.setDate(today.getDate() - 30)
  const targetStr = target.toISOString().slice(0, 10)
  // Pick the oldest entry that's <= target, or just the oldest available
  const past = entries.filter(e => e.date <= targetStr).at(-1) ?? entries[0]
  const pastScore = past?.scores?.[key]?.us
  if (pastScore === undefined) return undefined
  const usDelta = Math.round((currentUs - pastScore) * 10) / 10
  const direction: Trend['direction'] = usDelta > 0.1 ? 'up' : usDelta < -0.1 ? 'down' : 'flat'
  return { usDelta, direction }
}

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
  investment: 'Investment',
}

const METHODOLOGY_URL = 'https://us-china-ai-race.vercel.app/docs/methodology.html'

const TAB_SOURCES: Record<string, DimensionSource[]> = {
  frontier_models: [
    { label: 'LMSYS Chatbot Arena', url: 'https://chat.lmsys.org/' },
    { label: 'Epoch AI — Notable AI Models', url: 'https://epoch.ai/data/notable-ai-models' },
    { label: 'Hugging Face Hub', url: 'https://huggingface.co/models' },
    { label: 'ModelScope (魔搭社区)', url: 'https://modelscope.cn/models' },
  ],
  talent: [
    { label: 'OpenAlex API', url: 'https://api.openalex.org/works' },
    { label: 'MacroPolo AI Talent Tracker', url: 'https://macropolo.org/digital-projects/the-global-ai-talent-tracker/' },
    { label: 'NSF Survey of Earned Doctorates 2022', url: 'https://ncses.nsf.gov/pubs/nsf24300' },
    { label: 'China MoE Education Statistics (教育部统计数据)', url: 'http://www.moe.gov.cn/jyb_sjzl/moe_560/2022/' },
  ],
  compute: [
    { label: 'TOP500', url: 'https://www.top500.org' },
    { label: 'Epoch AI — Frontier Data Centers', url: 'https://epoch.ai/data' },
    { label: 'IEA — Energy and AI 2025', url: 'https://www.iea.org/reports/energy-and-ai' },
    { label: 'NVIDIA Geographic Revenue', url: 'http://bullfincher.io/companies/nvidia-corporation/revenue-by-geography' },
  ],
  adoption: [
    { label: 'SAS / Coleman Parkes Global Gen-AI Survey 2024', url: 'https://www.reuters.com/technology/artificial-intelligence/china-leads-world-adoption-generative-ai-survey-shows-2024-07-09/' },
    { label: 'IFR World Robotics 2024', url: 'https://ifr.org/ifr-press-releases/news/robot-density-nearly-doubled-globally' },
    { label: 'OECD ICT Access and Usage Database', url: 'https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html' },
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
  investment: [
    { label: 'Stanford AI Index 2025 (PitchBook)', url: 'https://hai.stanford.edu/ai-index/2025-ai-index-report/economy' },
    { label: 'SEC EDGAR XBRL API', url: 'https://data.sec.gov/api/xbrl/companyconcept/' },
    { label: 'NITRD AI R&D Budget Supplement', url: 'https://www.nitrd.gov/budgetinformation/' },
  ],
}

// ── Main export ───────────────────────────────────────────────────────────────

export interface LiveData {
  scorecardDimensions: ScoreCardDimension[]
  radarData: RadarDimension[]
  strategicInsights: StrategicInsight[]
  dimensionTabs: DimensionTab[]
  currentRead: string
}

export async function getLiveData(): Promise<LiveData> {
  const [exec, fm, tal, comp, adp, dif, eng, inv, hist]: [
    ExecutiveSummary, FrontierModels, Talent, Compute, Adoption, Diffusion, Energy, Investment, History | null
  ] = await Promise.all([
    fetchJson('executive_summary.json'),
    fetchJson('frontier_models.json'),
    fetchJson('talent.json'),
    fetchJson('compute.json'),
    fetchJson('adoption.json'),
    fetchJson('diffusion.json'),
    fetchJson('energy.json'),
    fetchJson('investment.json'),
    fetchJson('history.json').catch(() => null),
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
    trend: computeTrend(d.key, d.us_score, hist),
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
  const fmUs     = fm.summary.US
  const fmCn     = fm.summary.China
  const fmUsComp = fmUs.composite_score
  const fmCnComp = fmCn.composite_score
  const fmLeader = fmUsComp >= fmCnComp ? 'US' : 'China'

  // Detect schema version — v2.0 has release_activity / benchmark_performance / ecosystem_breadth;
  // v1.x has capability / output. Normalize to a common set of display values.
  const fmIsV2 = !!(fmUs.proxies?.release_activity || fmUs.proxies?.benchmark_performance)

  // Benchmark proxy (Arena + Epoch) — v2.0: benchmark_performance; v1.x: capability
  const fmBmUs = fmIsV2 ? fmUs.proxies.benchmark_performance : fmUs.proxies.capability
  const fmBmCn = fmIsV2 ? fmCn.proxies.benchmark_performance : fmCn.proxies.capability
  const fmBmUsShare  = fmBmUs?.share_score ?? 0
  const fmBmCnShare  = fmBmCn?.share_score ?? 0
  const fmArenaUsCount = (fmIsV2 ? (fmBmUs as FrontierBenchmark)?.arena_in_top20 : fmBmUs?.raw_value) ?? 0
  const fmArenaCnCount = (fmIsV2 ? (fmBmCn as FrontierBenchmark)?.arena_in_top20 : fmBmCn?.raw_value) ?? 0
  const fmEpochUsCount = (fmIsV2 ? (fmBmUs as FrontierBenchmark)?.epoch_notable_count : undefined) ?? 0
  const fmEpochCnCount = (fmIsV2 ? (fmBmCn as FrontierBenchmark)?.epoch_notable_count : undefined) ?? 0

  // Release activity proxy — v2.0: release_activity; v1.x: output
  const fmRaUs = fmIsV2 ? fmUs.proxies.release_activity : fmUs.proxies.output
  const fmRaCn = fmIsV2 ? fmCn.proxies.release_activity : fmCn.proxies.output
  const fmRaUsShare  = fmRaUs?.share_score ?? 0
  const fmRaCnShare  = fmRaCn?.share_score ?? 0
  const fmRaUsCount  = fmRaUs?.raw_value ?? 0
  const fmRaCnCount  = fmRaCn?.raw_value ?? 0
  const fmHfUsCount  = (fmIsV2 ? (fmRaUs as FrontierReleaseActivity)?.hf_count : fmRaUs?.raw_value) ?? fmRaUsCount
  const fmHfCnCount  = (fmIsV2 ? (fmRaCn as FrontierReleaseActivity)?.hf_count : fmRaCn?.raw_value) ?? fmRaCnCount
  const fmSuppCnCount = (fmIsV2 ? (fmRaCn as FrontierReleaseActivity)?.supplement_count : undefined) ?? 0

  // Ecosystem breadth proxy — v2.0 only
  const fmEcoUs = fmIsV2 ? fmUs.proxies.ecosystem_breadth : undefined
  const fmEcoCn = fmIsV2 ? fmCn.proxies.ecosystem_breadth : undefined
  const fmEcoUsShare = (fmEcoUs as FrontierEcosystem | undefined)?.share_score ?? 0
  const fmEcoCnShare = (fmEcoCn as FrontierEcosystem | undefined)?.share_score ?? 0

  // Leaderboard counts
  const fmLeaderboard = fm.leaderboard
  const fmArenaUsLb   = fmLeaderboard?.us_count    ?? fmArenaUsCount
  const fmArenaCnLb   = fmLeaderboard?.china_count ?? fmArenaCnCount

  // Coverage note from data (or default)
  const fmCoverageNote = fm.coverage_note ??
    'HuggingFace Hub alone undercounts China — ModelScope and domestic platforms not captured.'

  const talUs = tal.summary.US
  const talCn = tal.summary.China
  const talUsComposite = talUs.composite_score
  const talCnComposite = talCn.composite_score
  const talLeader = talUsComposite >= talCnComposite ? 'US' : 'China'
  const talIsV2 = tal.schema_version === '2.0' && !!(talUs.proxies?.research_output)

  // v2.0 proxies
  const talRoUs = talUs.proxies?.research_output
  const talRoCn = talCn.proxies?.research_output
  const talPlUs = talUs.proxies?.pipeline
  const talPlCn = talCn.proxies?.pipeline
  const talEmUs = talUs.proxies?.elite_migration
  const talEmCn = talCn.proxies?.elite_migration

  // Research output sub-signals (v2.0)
  const talVolUsShare   = talIsV2 ? (talRoUs?.paper_volume?.share_score ?? 0) : (talUs.proxies?.paper_volume?.share_score ?? 0)
  const talVolCnShare   = talIsV2 ? (talRoCn?.paper_volume?.share_score ?? 0) : (talCn.proxies?.paper_volume?.share_score ?? 0)
  const talVolUsRaw     = talIsV2 ? (talRoUs?.paper_volume?.raw_value ?? 0) : (talUs.proxies?.paper_volume?.raw_value ?? 0)
  const talVolCnRaw     = talIsV2 ? (talRoCn?.paper_volume?.raw_value ?? 0) : (talCn.proxies?.paper_volume?.raw_value ?? 0)
  const talHiUsShare    = talIsV2 ? (talRoUs?.high_impact?.share_score ?? 0) : (talUs.proxies?.high_impact?.share_score ?? 0)
  const talHiCnShare    = talIsV2 ? (talRoCn?.high_impact?.share_score ?? 0) : (talCn.proxies?.high_impact?.share_score ?? 0)
  const talHiUsRaw      = talIsV2 ? (talRoUs?.high_impact?.raw_value ?? 0) : (talUs.proxies?.high_impact?.raw_value ?? 0)
  const talHiCnRaw      = talIsV2 ? (talRoCn?.high_impact?.raw_value ?? 0) : (talCn.proxies?.high_impact?.raw_value ?? 0)
  const talTcUsShare    = talRoUs?.top_cited?.share_score ?? 0
  const talTcCnShare    = talRoCn?.top_cited?.share_score ?? 0
  const talTcUsRaw      = talRoUs?.top_cited?.raw_value ?? 0
  const talTcCnRaw      = talRoCn?.top_cited?.raw_value ?? 0
  const talRoUsShare    = talIsV2 ? (talRoUs?.share_score ?? 0) : talVolUsShare
  const talRoCnShare    = talIsV2 ? (talRoCn?.share_score ?? 0) : talVolCnShare

  // Pipeline proxy (v2.0)
  const talPlUsShare    = talPlUs?.share_score ?? 0
  const talPlCnShare    = talPlCn?.share_score ?? 0
  const talPlUsPhd      = talPlUs?.phd_annual ?? 0
  const talPlCnPhd      = talPlCn?.phd_annual ?? 0

  // Elite/migration proxy (v2.0)
  const talEmUsShare    = talEmUs?.share_score ?? 0
  const talEmCnShare    = talEmCn?.share_score ?? 0
  const talEmUsCount    = talEmUs?.researcher_count_est ?? 0
  const talEmCnCount    = talEmCn?.researcher_count_est ?? 0
  const talEmMigNote    = talEmUs?.migration_note ?? ''

  // Legacy compat (v1.x had top_conference not research_output)
  const talConfUsShare  = !talIsV2 ? (talUs.proxies?.top_conference?.share_score ?? talHiUsShare) : talTcUsShare
  const talConfCnShare  = !talIsV2 ? (talCn.proxies?.top_conference?.share_score ?? talHiCnShare) : talTcCnShare

  // Schema detection — v2.0 has composite_score at summary.US level
  const compIsV2 = comp.schema_version === '2.0' && !!(comp.summary.US as ComputeCountryV2).composite_score

  // v2.0 proxy shortcuts
  const compV2Us    = compIsV2 ? comp.summary.US as ComputeCountryV2 : null
  const compV2Cn    = compIsV2 ? comp.summary.China as ComputeCountryV2 : null
  const compUsComp  = compV2Us?.composite_score ?? 0
  const compCnComp  = compV2Cn?.composite_score ?? 0

  const compTcUs    = compV2Us?.proxies?.training_compute
  const compTcCn    = compV2Cn?.proxies?.training_compute
  const compHwUs    = compV2Us?.proxies?.hardware_supply
  const compHwCn    = compV2Cn?.proxies?.hardware_supply
  const compHpcUs   = compV2Us?.proxies?.visible_hpc
  const compHpcCn   = compV2Cn?.proxies?.visible_hpc

  const hiddenBand  = comp.hidden_compute_band ?? null

  // Legacy: Epoch AI training compute (pre-v2.0) — with TOP500 fallback
  const legacyUs = comp.summary.US as { training_compute_flop?: number; model_count?: number; rmax_pflops?: number; systems?: number; top500_rmax_pflops?: number; top500_systems?: number }
  const legacyCn = comp.summary.China as { training_compute_flop?: number; model_count?: number; rmax_pflops?: number; systems?: number; top500_rmax_pflops?: number; top500_systems?: number }
  const compUsFlop     = !compIsV2 ? legacyUs.training_compute_flop : undefined
  const compCnFlop     = !compIsV2 ? legacyCn.training_compute_flop : undefined
  const compUsModels   = compIsV2 ? (compTcUs?.model_count ?? 0) : (legacyUs.model_count ?? 0)
  const compCnModels   = compIsV2 ? (compTcCn?.model_count ?? 0) : (legacyCn.model_count ?? 0)
  const epochOk        = compIsV2 ? !!(compTcUs?.share_score) : (compUsFlop != null && compCnFlop != null)
  const compFlopTotal  = (!compIsV2 && epochOk) ? (compUsFlop! + compCnFlop!) : 1

  // TOP500 (supplementary for all schema versions)
  const top500Data     = comp.top500 ?? null
  const legacySystems  = comp.top_systems ?? null
  const compEdition    = top500Data?.list_edition ?? comp.list_edition ?? 'Nov 2025'
  const compUsRmax    = top500Data?.summary?.US?.rmax_pflops
    ?? legacyUs.top500_rmax_pflops
    ?? legacyUs.rmax_pflops
    ?? (compIsV2 ? (compHpcUs?.top500_rmax_pflops ?? 0) : 0)
  const compCnRmax    = top500Data?.summary?.China?.rmax_pflops
    ?? legacyCn.top500_rmax_pflops
    ?? legacyCn.rmax_pflops
    ?? (compIsV2 ? (compHpcCn?.top500_rmax_pflops ?? 0) : 0)
  const compRmaxTotal  = compUsRmax + compCnRmax
  const compUsSystems = top500Data?.summary?.US?.systems
    ?? legacyUs.top500_systems
    ?? legacyUs.systems
    ?? 0
  const compCnSystems = top500Data?.summary?.China?.systems
    ?? legacyCn.top500_systems
    ?? legacyCn.systems
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

  const invUs = inv.summary.US
  const invCn = inv.summary.China
  const invUsComp = invUs.composite_score
  const invCnComp = invCn.composite_score
  const privSeries = inv.private_investment.series
  const capexUs = inv.hyperscaler_capex.us_total_usd_b
  const capexCn = inv.hyperscaler_capex.china_total_usd_b
  const govUsTotal = inv.gov_rd.us.total_ai_usd_b
  const govUsLatestFy = inv.gov_rd.us.latest_fy
  const govCnEst = inv.gov_rd.china.estimate_usd_b
  const govCnRange = inv.gov_rd.china.range_usd_b

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
        ? `US leads on open model ecosystem index: ${fmUsComp.toFixed(1)} vs ${fmCnComp.toFixed(1)}`
        : `China leads on open model ecosystem index: ${fmCnComp.toFixed(1)} vs ${fmUsComp.toFixed(1)}`,
      headlineNote: fmIsV2
        ? 'Release activity (35%) + benchmark performance (45%) + ecosystem breadth (20%) — open models only, not closed-model capability'
        : 'Arena Elo capability ranking (60%) + Epoch AI notable model output (40%)',
      explanation: getCaveat('frontier_models') + '\n\nCoverage note: ' + fmCoverageNote,
      barData: [
        { label: 'Benchmark performance share — Arena + Epoch (%)', US: Math.round(fmBmUsShare), CN: Math.round(fmBmCnShare) },
        { label: 'Release activity share — HF Hub + ModelScope (%)', US: Math.round(fmRaUsShare), CN: Math.round(fmRaCnShare) },
        ...(fmIsV2 ? [{ label: 'Ecosystem breadth share — HF + ModelScope (%)', US: Math.round(fmEcoUsShare), CN: Math.round(fmEcoCnShare) }] : []),
        { label: 'Composite score', US: Math.round(fmUsComp), CN: Math.round(fmCnComp) },
      ],
      barXLabel: 'Share of combined US + China (%)',
      tableRows: [
        { label: 'Models in top 20 (LMSYS Arena Elo)',       us: fmt(fmArenaUsLb),   cn: fmt(fmArenaCnLb) },
        ...(fmIsV2 && fmEpochUsCount > 0 ? [{ label: 'Notable models 2y (Epoch AI)',           us: fmt(fmEpochUsCount), cn: fmt(fmEpochCnCount) }] : []),
        { label: 'HF Hub active models (30d)',                us: fmt(fmHfUsCount),   cn: fmt(fmHfCnCount) },
        ...(fmIsV2 && fmSuppCnCount > 0 ? [{ label: 'ModelScope supplement (est.)',             us: '—', cn: `~${fmt(fmSuppCnCount)}` }] : []),
        ...(fmIsV2 ? [{ label: 'Ecosystem breadth share (%)', us: `${Math.round(fmEcoUsShare)}%`, cn: `${Math.round(fmEcoCnShare)}%` }] : []),
        { label: 'Score (0–10)', ...getScore('frontier_models') },
      ],
      sources: TAB_SOURCES.frontier_models,
    },
    {
      id: 'talent',
      label: 'Talent',
      headline: talIsV2
        ? (talLeader === 'US'
            ? `US leads on talent pipeline index: ${talUsComposite.toFixed(1)} vs ${talCnComposite.toFixed(1)}`
            : Math.abs(talUsComposite - talCnComposite) < 1
              ? `Talent race near-tied: US ${talUsComposite.toFixed(1)} vs China ${talCnComposite.toFixed(1)}`
              : `China leads on talent pipeline index: ${talCnComposite.toFixed(1)} vs ${talUsComposite.toFixed(1)}`)
        : (talLeader === 'US'
            ? `US leads on talent composite: ${talUsComposite.toFixed(1)} vs ${talCnComposite.toFixed(1)}`
            : `China leads on talent composite: ${talCnComposite.toFixed(1)} vs ${talUsComposite.toFixed(1)}`),
      headlineNote: talIsV2
        ? 'Research output quality (35%) + domestic PhD pipeline (25%) + elite researchers + migration (40%)'
        : 'paper volume (30%) + quality papers cited ≥25 (40%) + high-impact cited ≥100 (30%)',
      explanation: getCaveat('talent') + (tal.coverage_warning ? '\n\nCoverage note: ' + tal.coverage_warning : ''),
      barData: talIsV2
        ? [
            { label: 'Research output quality — papers + citations (%)', US: Math.round(talRoUsShare),  CN: Math.round(talRoCnShare)  },
            { label: 'Domestic talent pipeline — PhD graduates (%)',      US: Math.round(talPlUsShare),  CN: Math.round(talPlCnShare)  },
            { label: 'Elite researchers at US/China institutions (%)',     US: Math.round(talEmUsShare),  CN: Math.round(talEmCnShare)  },
            { label: 'Composite score (%)',                               US: Math.round(talUsComposite), CN: Math.round(talCnComposite) },
          ]
        : [
            { label: 'Paper volume share (%)',            US: Math.round(talVolUsShare),  CN: Math.round(talVolCnShare)  },
            { label: 'Quality papers share (cited ≥25%)', US: Math.round(talConfUsShare), CN: Math.round(talConfCnShare) },
            { label: 'High-impact papers share (%)',      US: Math.round(talHiUsShare),   CN: Math.round(talHiCnShare)   },
            { label: 'Composite score',                   US: Math.round(talUsComposite), CN: Math.round(talCnComposite) },
          ],
      barXLabel: 'Share of combined US + China (%)',
      tableRows: talIsV2
        ? [
            { label: 'AI papers (12m, OpenAlex)',              us: fmt(talVolUsRaw),       cn: fmt(talVolCnRaw) },
            { label: 'High-impact papers (cited ≥50, 3y)',     us: fmt(talHiUsRaw),        cn: fmt(talHiCnRaw) + (talRoUs?.high_impact?.data_ok === false ? ' (est.)' : '') },
            { label: 'Top-cited papers (cited ≥25, 2y)',       us: fmt(talTcUsRaw),        cn: fmt(talTcCnRaw) + (talRoUs?.top_cited?.data_ok === false ? ' (est.)' : '') },
            { label: 'Annual AI/CS PhDs (est.)',               us: `~${fmt(talPlUsPhd)}`,  cn: `~${fmt(talPlCnPhd)}` },
            { label: 'Elite researchers (MacroPolo 2023)',     us: `~${fmt(talEmUsCount)} (${Math.round(talEmUsShare)}%)`, cn: `~${fmt(talEmCnCount)} (${Math.round(talEmCnShare)}%)` },
            ...(talEmMigNote ? [{ label: 'China-origin researchers at US institutions', us: '~36% of China-undergrad cohort', cn: '~34% (up from 25% in 2019)' }] : []),
            { label: 'Score (0–10)', ...getScore('talent') },
          ]
        : [
            { label: 'AI papers (12-month)',               us: fmt(talVolUsRaw),  cn: fmt(talVolCnRaw)  },
            { label: 'Quality papers cited ≥25 (2y)',        us: fmt(talConfUsShare > 0 ? Math.round(talConfUsShare) : 0), cn: fmt(talConfCnShare > 0 ? Math.round(talConfCnShare) : 0) },
            { label: 'High-impact papers cited ≥100 (3y)',  us: fmt(talHiUsRaw),  cn: fmt(talHiCnRaw)  },
            { label: 'Score (0–10)', ...getScore('talent') },
          ],
      sources: TAB_SOURCES.talent,
    },
    {
      id: 'compute',
      label: 'Compute',
      headline: compIsV2
        ? `US leads on triangulated compute index: ${compUsComp.toFixed(1)}% vs ${compCnComp.toFixed(1)}%`
        : epochOk
          ? `US accounts for ${pct(compUsFlop!, compFlopTotal)}% of disclosed AI training compute`
          : `US holds ${pct(compUsRmax, compRmaxTotal)}% of disclosed TOP500 compute`,
      headlineNote: compIsV2
        ? `Training compute (40%) + hardware supply (40%) + visible HPC (20%) — scored composite is a conservative lower bound`
        : epochOk
          ? `Notable models since ${epochCutoff.slice(0,4)} — US ${compUsModels} models, China ${compCnModels} models (Epoch AI)`
          : `${fmt(Math.round(compUsRmax))} vs ${fmt(Math.round(compCnRmax))} PFlops (TOP500, ${compEdition})`,
      explanation: compIsV2
        ? getCaveat('compute') + (hiddenBand ? `\n\nHidden compute estimate: China's true share of combined US+China compute is likely ${hiddenBand.china_lower_pct}–${hiddenBand.china_upper_pct}% (point est. ${hiddenBand.china_point_pct}%). ${hiddenBand.narrative ?? ''}` : '')
        : epochOk
          ? `Epoch AI tracks training compute (FLOPs) for notable AI models globally. Since ${epochCutoff.slice(0,4)}, US labs account for ~${pct(compUsFlop!, compFlopTotal)}% of disclosed training compute vs China's ~${pct(compCnFlop!, compFlopTotal)}%. This understates China's real position: frontier closed models (Qwen-max, Doubao) and Huawei Ascend deployments do not disclose compute. Analyst estimates put the real frontier AI compute gap at roughly 3–5×, not the 6× implied by disclosed figures alone.`
          : getCaveat('compute'),
      barData: compIsV2
        ? [
            { label: 'Training compute share — Epoch AI disclosed (%)',      US: Math.round(compTcUs?.share_score ?? 85), CN: Math.round(compTcCn?.share_score ?? 15) },
            { label: 'Hardware supply share — NVIDIA + Ascend adj. (%)',     US: Math.round(compHwUs?.share_score ?? 68), CN: Math.round(compHwCn?.share_score ?? 32) },
            { label: 'Visible HPC share — TOP500 + corrections (%)',         US: Math.round(compHpcUs?.share_score ?? 73), CN: Math.round(compHpcCn?.share_score ?? 28) },
            { label: 'Composite score (%)',                                   US: Math.round(compUsComp), CN: Math.round(compCnComp) },
          ]
        : epochOk
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
        ...(compIsV2 ? [
          { label: 'Training compute share (Epoch AI, 2023+)', us: `${Math.round(compTcUs?.share_score ?? 85)}%`, cn: `${Math.round(compTcCn?.share_score ?? 15)}% (disclosed only)` },
          { label: 'Notable models tracked (since 2023)',       us: String(compUsModels), cn: String(compCnModels) },
          { label: 'NVIDIA data center revenue (FY2025)',        us: `$${compHwUs?.nvidia_revenue_usd_b ?? '—'}B`, cn: `$${compHwCn?.nvidia_revenue_usd_b ?? '—'}B` },
          { label: 'Huawei Ascend equivalent value (est.)',      us: '—', cn: `~$${compHwCn?.ascend_equivalent_usd_b ?? '—'}B (analyst est.)` },
          { label: `TOP500 Rmax — ${compEdition} (disclosed)`,  us: `${fmt(Math.round(compUsRmax))} PFlops`, cn: `${fmt(Math.round(compCnRmax))} PFlops` },
          ...(compHpcCn?.non_top500_correction_pflops ? [{ label: 'China HPC correction (non-TOP500)', us: `+${fmt(compHpcUs?.private_cluster_addition_pflops ?? 2300)} PFlops (private)`, cn: `+${fmt(compHpcCn.non_top500_correction_pflops)} PFlops (est.)` }] : []),
          ...(hiddenBand ? [{ label: 'Hidden compute estimate (China)', us: `${hiddenBand.us_lower_pct}–${hiddenBand.us_upper_pct}% (est.)`, cn: `${hiddenBand.china_lower_pct}–${hiddenBand.china_upper_pct}% (est., vs ${Math.round(compCnComp)}% scored)` }] : []),
        ] : [
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
        ]),
        { label: 'Score (0–10)', ...getScore('compute') },
      ],
      sources: TAB_SOURCES.compute,
    },
    {
      id: 'adoption',
      label: 'Adoption',
      headline: `China leads on AI adoption: composite ${adpCn.composite_score.toFixed(1)} vs ${adpUs.composite_score.toFixed(1)}`,
      headlineNote: 'gen-AI adoption rate (SAS 2024) + industrial robot density',
      explanation: getCaveat('adoption'),
      barData: [
        {
          label: 'Gen-AI adoption (%)',
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
          label: 'Gen-AI adoption (SAS 2024)',
          us: `${adpUs.proxies.enterprise_adoption.raw_value}%`,
          cn: `${adpCn.proxies.enterprise_adoption.raw_value}%`,
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
    {
      id: 'investment',
      label: 'Investment',
      headline: `US leads on AI investment: composite ${invUsComp.toFixed(1)}% vs ${invCnComp.toFixed(1)}%`,
      headlineNote: `Private AI capital (70%) + hyperscaler capex (30%) — ${inv.private_investment.latest_year} data`,
      explanation: getCaveat('investment'),
      barData: [
        {
          label: `Private AI capital (${inv.private_investment.latest_year}, $B)`,
          US: Math.round(invUs.private_investment_usd_b * 10) / 10,
          CN: Math.round(invCn.private_investment_usd_b * 10) / 10,
        },
        {
          label: 'Hyperscaler capex ($B, latest annual)',
          US: Math.round(capexUs * 10) / 10,
          CN: Math.round(capexCn * 10) / 10,
        },
        {
          label: 'Investment composite share (%)',
          US: Math.round(invUsComp),
          CN: Math.round(invCnComp),
        },
      ],
      barXLabel: 'US vs China',
      tableRows: [
        {
          label: `Private AI investment (${inv.private_investment.latest_year})`,
          us: `$${invUs.private_investment_usd_b}B`,
          cn: `$${invCn.private_investment_usd_b}B`,
        },
        {
          label: 'Hyperscaler AI capex (latest annual)',
          us: `$${capexUs.toFixed(1)}B`,
          cn: `$${capexCn.toFixed(1)}B`,
        },
        {
          label: `Gov't AI R&D (${govUsLatestFy} est.)`,
          us: `$${govUsTotal.toFixed(3)}B (NITRD)`,
          cn: `~$${govCnEst}B (CSET est., $${govCnRange[0]}–${govCnRange[1]}B range)`,
        },
        {
          label: 'Private investment trend (2020→2024)',
          us: `$${privSeries.find(s => s.year === 2020)?.us_usd_b ?? '—'}B → $${privSeries.find(s => s.year === 2024)?.us_usd_b ?? '—'}B`,
          cn: `$${privSeries.find(s => s.year === 2020)?.china_usd_b ?? '—'}B → $${privSeries.find(s => s.year === 2024)?.china_usd_b ?? '—'}B`,
        },
        { label: 'Score (0–10)', ...getScore('investment') },
      ],
      sources: TAB_SOURCES.investment,
    },
  ]

  const currentRead: string = exec.current_read ?? ''

  return { scorecardDimensions, radarData, strategicInsights, dimensionTabs, currentRead }
}
