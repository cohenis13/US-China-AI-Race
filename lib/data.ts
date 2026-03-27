export type Confidence = 'high' | 'medium' | 'low'
export type Leader = 'US' | 'CN' | 'Tied'

export interface ScoreCardDimension {
  id: string
  label: string
  usScore: number
  cnScore: number
  leader: Leader
  delta: number
  confidence: Confidence
}

export interface RadarDimension {
  dimension: string
  US: number
  CN: number
  confidence: Confidence
  caveat: string
}

export interface BarDataPoint {
  label: string
  US: number
  CN: number
}

export interface AdoptionSignal {
  signal: string
  usStatus: 'OK' | 'PARTIAL' | 'NO DATA'
  cnStatus: 'OK' | 'PARTIAL' | 'NO DATA'
  note?: string
}

export interface DimensionSource {
  label: string
  url: string
}

export interface DimensionTab {
  id: string
  label: string
  headline: string
  headlineNote?: string
  explanation: string
  barData?: BarDataPoint[]
  barXLabel?: string
  adoptionSignals?: AdoptionSignal[]
  tableRows?: { label: string; us: string; cn: string }[]
  sources?: DimensionSource[]
}

// ─── Scorecard data ───────────────────────────────────────────────────────────
export const scorecardDimensions: ScoreCardDimension[] = [
  { id: 'frontier', label: 'Frontier Models', usScore: 9, cnScore: 7, leader: 'US', delta: 2, confidence: 'high' },
  { id: 'compute',  label: 'Compute',         usScore: 9, cnScore: 6, leader: 'US', delta: 3, confidence: 'high' },
  { id: 'talent',   label: 'Talent',          usScore: 8, cnScore: 7, leader: 'US', delta: 1, confidence: 'medium' },
  { id: 'adoption', label: 'Adoption',        usScore: 7, cnScore: 8, leader: 'CN', delta: 1, confidence: 'medium' },
  { id: 'diffusion',label: 'Diffusion',       usScore: 7, cnScore: 8, leader: 'CN', delta: 1, confidence: 'low' },
  { id: 'energy',   label: 'Energy',          usScore: 6, cnScore: 8, leader: 'CN', delta: 2, confidence: 'medium' },
]

// ─── Radar data ───────────────────────────────────────────────────────────────
export const radarData: RadarDimension[] = [
  { dimension: 'Frontier Models', US: 9, CN: 7, confidence: 'medium', caveat: '' },
  { dimension: 'Compute',         US: 9, CN: 6, confidence: 'high',   caveat: '' },
  { dimension: 'Talent',          US: 8, CN: 7, confidence: 'medium', caveat: '' },
  { dimension: 'Adoption',        US: 7, CN: 8, confidence: 'low',    caveat: '' },
  { dimension: 'Diffusion',       US: 7, CN: 8, confidence: 'low',    caveat: '' },
  { dimension: 'Energy',          US: 6, CN: 8, confidence: 'high',   caveat: '' },
]

// ─── Strategic insights ───────────────────────────────────────────────────────
export interface StrategicInsight {
  bold: string
  rest: string
}

export const strategicInsights: StrategicInsight[] = [
  { bold: 'US leads', rest: ' at the technological frontier and advanced compute.' },
  { bold: 'China leads', rest: ' in energy infrastructure and industrial-scale adoption.' },
  { bold: 'Diffusion speed', rest: ' may matter more than peak model performance.' },
  { bold: 'Key bottlenecks:', rest: ' chip access (China), power capacity (US).' },
]

// ─── Dimension tabs ───────────────────────────────────────────────────────────
export const dimensionTabs: DimensionTab[] = [
  {
    id: 'frontier',
    label: 'Frontier Models',
    headline: 'US leads on every major public benchmark',
    headlineNote: 'as of Q1 2026',
    explanation:
      'GPT-5 and Claude Opus 4 remain ahead of DeepSeek V3 and Qwen 3 on reasoning, coding, and multimodal tasks. The gap has narrowed significantly since 2024.',
    barData: [
      { label: 'MMLU', US: 92, CN: 86 },
      { label: 'HumanEval', US: 90, CN: 81 },
      { label: 'MATH', US: 88, CN: 83 },
      { label: 'GPQA', US: 82, CN: 74 },
    ],
    barXLabel: 'Benchmark score (%)',
    tableRows: [
      { label: 'Top frontier model', us: 'GPT-5 / Claude Opus 4', cn: 'DeepSeek V3 / Qwen 3' },
      { label: 'Open-weight models', us: 'Llama 4', cn: 'DeepSeek R2' },
      { label: 'Multimodal', us: 'GPT-5 Vision', cn: 'Qwen-VL' },
    ],
  },
  {
    id: 'talent',
    label: 'Talent',
    headline: 'US attracts more top-tier researchers globally',
    headlineNote: 'measured by top-venue publications',
    explanation:
      'The US benefits from global immigration of ML talent. China produces the most domestic graduates but loses many to US labs. Diaspora retention is a growing strategic lever.',
    barData: [
      { label: 'NeurIPS papers', US: 38, CN: 27 },
      { label: 'ICML papers',    US: 35, CN: 29 },
      { label: 'PhD graduates',  US: 42, CN: 58 },
      { label: 'Industry hires', US: 55, CN: 32 },
    ],
    barXLabel: 'Share (%)',
    tableRows: [
      { label: 'Top AI labs', us: 'OpenAI, Anthropic, Google DeepMind', cn: 'Zhipu, Moonshot, ByteDance' },
      { label: 'Retention risk', us: 'Low', cn: 'Medium — emigration to US' },
    ],
  },
  {
    id: 'compute',
    label: 'Compute',
    headline: 'US holds a 3–4× lead in frontier GPU capacity',
    headlineNote: 'H100-equivalent units, estimated',
    explanation:
      'Export controls constrain China to H800/A800 chips and domestic Huawei Ascend alternatives. US clusters at Microsoft, Google, and AWS are significantly larger.',
    barData: [
      { label: 'Frontier clusters',    US: 90, CN: 40 },
      { label: 'Cloud AI capacity',    US: 78, CN: 52 },
      { label: 'Domestic chip supply', US: 85, CN: 48 },
      { label: 'Edge deployment',      US: 65, CN: 70 },
    ],
    barXLabel: 'Relative capacity index (0–100)',
    tableRows: [
      { label: 'Primary GPU', us: 'NVIDIA H100/H200', cn: 'Huawei Ascend 910B' },
      { label: 'Export controls', us: 'Restrictor', cn: 'Subject to BIS controls' },
      { label: 'Domestic fab', us: 'TSMC (partner)', cn: 'SMIC (limited EUV)' },
    ],
  },
  {
    id: 'adoption',
    label: 'Adoption',
    headline: 'China leads in government-coordinated AI deployment',
    headlineNote: 'based on available disclosures',
    explanation:
      'China\'s centralized procurement enables faster rollout across public sector and SOEs. US corporate deployment is broader but less coordinated. Coverage is limited — compare directionally.',
    adoptionSignals: [
      { signal: 'Government procurement', usStatus: 'PARTIAL', cnStatus: 'OK',     note: 'US federal AI contracts fragmented across agencies' },
      { signal: 'Corporate disclosures',  usStatus: 'OK',      cnStatus: 'PARTIAL', note: 'Chinese firms less likely to disclose AI spend' },
    ],
  },
  {
    id: 'constraints',
    label: 'Constraints',
    headline: 'Chip access (CN) and power capacity (US) are the primary bottlenecks',
    explanation:
      'China\'s compute growth is bounded by export controls on advanced semiconductors. The US faces datacenter permitting delays and grid interconnection backlogs that slow capacity expansion.',
    barData: [
      { label: 'Chip access',         US: 92, CN: 45 },
      { label: 'Power availability',  US: 55, CN: 75 },
      { label: 'Cooling capacity',    US: 68, CN: 72 },
      { label: 'Skilled workforce',   US: 80, CN: 70 },
    ],
    barXLabel: 'Constraint relief index (higher = fewer constraints)',
    tableRows: [
      { label: 'Primary constraint', us: 'Power / grid', cn: 'Advanced chips' },
      { label: 'Mitigation path', us: 'Nuclear + solar buildout', cn: 'Domestic fab (5–7 yr horizon)' },
    ],
  },
  {
    id: 'outlook',
    label: 'Outlook',
    headline: 'Structural US lead likely to persist through 2027',
    explanation:
      'Export controls remain the most durable US advantage. China\'s efficiency gains (e.g., DeepSeek) narrow the effective gap. Diffusion and adoption may equalize faster than frontier capability.',
    barData: [
      { label: 'Frontier (2026)',   US: 9, CN: 7 },
      { label: 'Frontier (2027e)',  US: 9, CN: 8 },
      { label: 'Adoption (2026)',   US: 7, CN: 8 },
      { label: 'Adoption (2027e)',  US: 8, CN: 9 },
    ],
    barXLabel: 'Estimated score (0–10)',
    tableRows: [
      { label: 'Most likely scenario', us: 'Maintains frontier lead', cn: 'Closes gap via efficiency' },
      { label: 'Key wildcard', us: 'AGI timeline', cn: 'Export control evasion' },
    ],
  },
]
