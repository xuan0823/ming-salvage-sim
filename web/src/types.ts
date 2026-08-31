import { Power } from "lucide-react";

export type Metrics = Record<string, number>;

export type Region = {
  id: string;
  name: string;
  kind: string;
  population: number;
  public_support: number;
  unrest: number;
  natural_disaster: string;
  human_disaster: string;
  registered_land: number;
  hidden_land: number;
  tax_per_turn: number;
  tax_actual?: number;
  tax_efficiency?: number;
  tax_breakdown?: Record<string, number>;
  fiscal?: Record<string, number | string>;
  grain_output?: number;
  grain_stock?: number;
  gentry_resistance: number;
  military_pressure: number;
  status: string;
  controlled_by?: string;
};

export type Army = {
  id: string;
  name: string;
  station: string;
  theater: string;
  commander: string;
  controller: string;
  troop_type: string;
  troop_composition?: Record<string, number>;
  manpower: number;
  maintenance_per_turn: number;
  supply: number;
  morale: number;
  training: number;
  equipment: number;
  arrears: number;
  mobility: number;
  loyalty: number;
  status: string;
  owner_power?: string;
  arms?: ArmyWeapon[];
};

export type ArmyWeapon = {
  troop_type: string;
  id: string;
  name: string;
  tier: string;
  qty: number;
};

export type ArmsStockItem = {
  id: string;
  name: string;
  tier: string;
  qty: number;
  unlocked: boolean;
  requires_tech: string;
};

export type Power = {
  id: string;
  name: string;
  kind: string;
  leader: string;
  stance: string;
  leverage: number;
  satisfaction: number;
  military_strength: number;
  cohesion: number;
  supply: number;
  agenda: string;
  status: string;
  last_action: string;
};

export type Building = {
  id: string;
  region_id: string;
  name: string;
  category: string;
  level: number;
  condition: number;
  maintenance: number;
  risk: number;
  output_metric: string;
  output_amount: number;
  status: string;
  origin: string;
};

export type Technology = {
  id: string;
  name: string;
  category: string;
  effect_summary: string;
  status: string;
  origin: string;
};

export type Department = {
  name: string;
  authority_scope: string;
  power: number;
  responsibility: number;
  corruption_risk: number;
};

export type PresetTreeItem = {
  key: string;
  name: string;
  category: string;
  effect_summary: string;
  authority_scope?: string;
  power?: number;
  expected_months: number;
  bar_value: number;
  requires: string[];
  unlocked: boolean;
  available: boolean;
};

export type PresetTrees = {
  technologies: PresetTreeItem[];
  departments: PresetTreeItem[];
};

export type MapNode = {
  id: string;
  kind: "region" | "theater" | "external";
  x: number;
  y: number;
  label?: string;
  risk: number;
  region?: Region;
  armies: Army[];
  buildings?: Building[];
  power?: Power;
};

export type RegionPathRenderItem = {
  id: string;
  name: string;
  controlledBy: string;
  unrest: number;
  risk: number;
  labelX: number;
  labelY: number;
  paths: Array<{ id: string; d: string }>;
};

export type ExternalPathRenderItem = {
  id: string;
  name: string;
  powerId: string;
  labelX: number;
  labelY: number;
  paths: Array<{ id: string; d: string }>;
};

export type SvgLabelPosition = {
  svgX: number;
  svgY: number;
};

export type Minister = {
  id?: string;
  name: string;
  office: string;  // 去职者已清空，可能为空串
  office_type: string;
  faction: string;
  aliases?: string[];
  personal_skills?: string[];
  loyalty?: number;
  ability?: number;
  integrity?: number;
  courage?: number;
  diplomacy?: number;
  martial?: number;
  stewardship?: number;
  intrigue?: number;
  learning?: number;
  style: string;
  location?: string;
  birth_year?: number;
  historical_death_year?: number;
  historical_death_month?: number;
  debut_year?: number;
  debut_month?: number;
  status: string;  // active/dismissed/imprisoned/exiled/retired/dead/offstage
  status_reason?: string;
  status_label: string;  // 中文：在朝/已罢黜/下狱/流放/致仕…
  summary: string;
  description?: string;
  favorite: boolean;
  portrait_id?: string;  // 空/undefined=无专属，前端 fallback 到池
  power_id?: string;     // 大明=ming, 后金=houjin, 流寇=bandits 等
  origin?: string;       // preset/runtime
  archived?: boolean;
  skills: Array<{ id: string; name: string; kind?: string; sources: string[]; description: string }>;
};

export type EventItem = {
  id: string;
  title: string;
  kind: string;
  summary: string;
  urgency: number;
  severity: number;
  credibility: number;
  interests: string[];
  audiences: string[];
};

export type Directive = {
  id: number;
  event_id: string;
  event_title: string;
  actor: string;
  skill_id: string;
  skill_name: string;
  text: string;
  source: string;
  status: string; // pending（待核定大臣拟旨）| draft（颁诏候选）
  notes: string;
};

export type StructuredDirectiveFieldSpec = {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "number";
  option_source?: "armies" | "regions" | "regions_or_all" | "weapons" | "people" | "departments" | "buildings" | "taxes";
  required?: boolean;
  required_when?: { field: string; values: string[] };
  placeholder?: string;
  options?: string[];
};

export type StructuredDirectiveTemplate = {
  id: string;
  label: string;
  category: string;
  settlement_hint: string;
  compiled_text: string;
  fields: StructuredDirectiveFieldSpec[];
};

export type StructuredDirective = {
  id: number;
  template_id: string;
  category: string;
  title: string;
  fields: Record<string, string>;
  compiled_text: string;
  settlement_hint: string;
  status: string;
};

export type Issue = {
  id: number;
  kind: "situation" | "initiative";
  title: string;
  bar_value: number;
  bar_good_meaning: string;
  bar_bad_meaning: string;
  phase: string;
  stage_text: string;
  severity: number;
  tags: string[];
  inertia: number;
  resolve_condition: string;
  fail_condition: string;
  ongoing_text: string;
  effect_on_resolve: Record<string, number>;
  effect_on_fail: Record<string, number>;
  origin_kind?: string;
  origin_ref?: string;
  status?: string;
  is_manual?: boolean;
  duration_turns?: number;
  goal?: string;
  assignee?: string;
  budget_pool?: number;       // 承办人专款余额（万两）
  budget_source?: string;     // 专款出库：'国库' / '内库' / ''
  death_authority?: boolean;  // 专断之权（生杀权）
  origin_turn?: number;
};

export type LegacyEffect = {
  国库?: number;
  内库?: number;
  民心?: number;
  皇威?: number;
  regions?: Record<string, Record<string, number>>;
  armies?: Record<string, Record<string, number>>;
};

export type Legacy = {
  id: number;
  name: string;
  narrative_hint: string;
  modifiers: LegacyEffect;
  effect_text: string;
  remaining_months: number;  // -1 = 永久
  clear_condition: string;
};

export type ClosedIssue = {
  id: number;
  kind: "situation" | "initiative";
  title: string;
  status: "resolved" | "failed" | "dropped";
  bar_value: number;
  bar_good_meaning: string;
  bar_bad_meaning: string;
  closed_turn: number;
  stage_text: string;
  effect: any;
};

export type BudgetItem = {
  name: string;
  amount: number;
  note: string;
  base_key?: string;
  rate_key?: string;
  base?: number;
  rate?: number;
  formula?: string;
  formula_kind?: string;
  basis?: string;
  basis_total?: number;
  rate_unit?: string;
  paid_estimate?: number;  // 各军军饷专用：受国库约束的预计实发（< amount 表示发不满、差额转欠饷）
};

export type BudgetMovement = {
  delta: number;
  balance_after: number;
  category: string;
  reason: string;
};

export type BudgetAccount = {
  balance: number;
  income: BudgetItem[];
  expense: BudgetItem[];
  income_total: number;
  expense_total: number;
  net: number;
  base_income_total?: number;
  base_expense_total?: number;
  base_net?: number;
  modifier_pct?: number;
  movements: BudgetMovement[];
  movements_total: number;
};

export type Budget = Record<"国库" | "内库", BudgetAccount>;

export type DecisionOption = {
  label: string;
  hint: string;
};

export type PendingDecision = {
  idx: number;
  title: string;
  context: string;
  options: DecisionOption[];
  choice?: { label?: string; hint?: string; note?: string } | null;
  status?: string;
};

export type GameState = {
  turn: { year: number; period: number; turn: number; phase?: string };
  metrics: Metrics;
  previous_summary: string;
  treasury: string;
  issues: Issue[];
  max_decree_issues?: number;
  issue_log_limit?: number;
  legacies: Legacy[];
  closed_this_turn: ClosedIssue[];
  budget: Budget;
  region_warning: string;
  army_warning: string;
  power_warning: string;
  powers: Power[];
  victory_status: { status: string; summary: string };
  ending: EndingPayload | null;
  events: EventItem[];
  regions: Region[];
  armies: Army[];
  buildings?: Building[];
  arms_stock?: ArmsStockItem[];
  departments: Department[];
  technologies: Technology[];
  preset_trees?: PresetTrees;
  troop_rates?: Record<string, number>;  // 兵种单价表，来自 troop_cost.json（前端不再硬编码）
  map_nodes: MapNode[];
  ministers: Minister[];
  archived_ministers?: Minister[];
  consorts: Minister[];
  directives: Directive[];
  structured_directives: StructuredDirective[];
  pending_count: number;
  pending_decisions?: PendingDecision[];
  last_decree: string;
  last_report: string;
};

export type EndingTimelineItem = {
  turn: number; year: number; period: number;
  decree_brief: string; effect_brief: string; chapter: string;
};

export type EndingPayload = {
  status: string; label: string; summary: string; timeline: EndingTimelineItem[];
};

export type ChatMessage = { role: "user" | "minister"; content: string };

export type CourtChatMessage = {
  role: "emperor" | "minister" | "conclusion";
  speaker: string;
  content: string;
  displayContent?: string;
  options?: string[];
};

export type CourtChatResponse = {
  turn: number;
  year: number;
  period: number;
  history: CourtChatMessage[];
};

export type ChatDisplayMessage = ChatMessage & { pending?: boolean };

export type Suggestion = { label: string; text: string; prefix?: boolean };

export type ModalName = "none" | "state" | "chat" | "edict" | "report" | "extraction" | "history" | "menu" | "secret_orders" | "ending" | "long_goals";

export type SaveEntry = { name: string; size: number; mtime: number };

export type LLMConfigInfo = {
  base_url: string;
  model: string;
  max_tokens: number;
  timeout_seconds: number;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  thinking_level: string;
  advanced_model: string;
  advanced_base_url: string;
  has_advanced_api_key: boolean;
  advanced_thinking_level: string;
  has_api_key: boolean;
  persisted: {
    base_url: string;
    model: string;
    has_api_key: boolean;
    max_tokens: number;
    timeout_seconds: number;
    connect_timeout_seconds: number;
    read_timeout_seconds: number;
    thinking_level: string;
    advanced_model: string;
    advanced_base_url: string;
    has_advanced_api_key: boolean;
    advanced_thinking_level: string;
  };
};

export type SecretOrder = {
  id: number;
  turn_issued: number;
  due_turn: number;
  year_issued: number;
  period_issued: number;
  minister_name: string;
  title: string;
  content: string;
  tags: string[];
  importance: number;
  status: "active" | "pending_review" | "done" | "failed" | "cancelled";
  result: string;
  sim_note: string;
  turn_closed: number | null;
};

export type ProposedDirective = { id: number; text: string; status: string; notes: string };

export type ChatResponse = {
  answer: string;
  history: ChatMessage[];
  suggestions: Suggestion[];
  directives: Directive[];
  pending_count?: number;
  court_action?: string;
  next_minister?: string;
  registered_minister?: string;
  proposed_directive?: ProposedDirective | null;
  secret_order_id?: number;
};

export type ApiErrorDetail = {
  code?: string;
  message?: string;
  provider_message?: string;
  status_code?: number | null;
};

export type AppView = "menu" | "game";

export type MenuSave = {
  name: string;
  size: number;
  mtime: number;
  campaign_id?: string;
  kind?: "auto" | "manual";
  label?: string;
  year?: number;
  period?: number;
  turn?: number;
  tag?: string;
};

export type MenuCampaign = {
  campaign_id: string;
  kind: "auto" | "manual";
  current: boolean;
  saves: MenuSave[];
  latest_mtime: number;
};

export type MenuStatus = {
  has_api_key: boolean;
  has_running_game: boolean;
  has_main_db: boolean;
  saves: MenuSave[];
  campaigns?: MenuCampaign[];
  current_campaign?: string;
  active_scenario?: ScenarioManifest | null;
  game_settings?: {
    hitl_min_decisions: number;
    court_chat_debate_rounds?: number;
    court_chat_stream_speed?: number;
    max_decree_issues?: number;
    issue_log_limit?: number;
    secret_order_person_limit?: number;
    secret_order_total_limit?: number;
    character_limit?: number;
    minister_temperature?: number;
    minister_top_p?: number;
    simulator_temperature?: number;
    simulator_top_p?: number;
    extractor_temperature?: number;
    extractor_top_p?: number;
  };
  llm: {
    base_url: string;
    model: string;
    has_api_key: boolean;
    max_tokens: number;
    timeout_seconds: number;
    connect_timeout_seconds: number;
    read_timeout_seconds: number;
    thinking_level: string;
    advanced_model: string;
    advanced_base_url: string;
    has_advanced_api_key: boolean;
    advanced_thinking_level: string;
  };
};

// ---- 自定义剧本 ----

export type ScenarioManifest = {
  id: string;
  name: string;
  description: string;
  created?: number;
  updated?: number;
  source?: "manual" | "generated";
  files: { characters: boolean; events: boolean; seed_events: boolean };
};

export type ScenarioFaction = {
  name: string;
  satisfaction: number;
  leverage: number;
  agenda: string;
};

export type ScenarioCharacter = {
  name: string;
  office: string;
  office_type: string;
  faction: string;
  loyalty: number;
  ability: number;
  integrity: number;
  courage: number;
  style: string;
  power_id: string;
  aliases?: string[];
  personal_skills?: string[];
  diplomacy?: number;
  martial?: number;
  stewardship?: number;
  intrigue?: number;
  learning?: number;
  location?: string;
  birth_year?: number;
  historical_death_year?: number;
  historical_death_month?: number;
  debut_year?: number;
  debut_month?: number;
  status?: string;
  summary?: string;
  portrait_id?: string;
  [key: string]: unknown;
};

export type ScenarioCharactersFile = {
  factions: ScenarioFaction[];
  characters: ScenarioCharacter[];
};

export type ScenarioEvent = {
  id: string;
  title: string;
  kind: string;
  summary: string;
  urgency: number;
  severity: number;
  credibility: number;
  interests: string[];
  audiences: string[];
  event_type: "situation" | "node" | "ending";
  precondition?: string;
  resolve_condition?: string;
  fail_condition?: string;
  trigger_year?: number;
  trigger_month?: number;
  is_historical?: boolean;
  require?: unknown;
  trigger_gate?: unknown;
  auto_trigger?: boolean;
  bar_value?: number;
  bar_good_meaning?: string;
  bar_bad_meaning?: string;
  inertia?: number;
  region_hint?: string;
  tags?: string[];
  [key: string]: unknown;
};

export type ScenarioFull = {
  manifest: ScenarioManifest;
  characters: ScenarioCharactersFile | null;
  events: ScenarioEvent[] | null;
  seed_events: ScenarioEvent[] | null;
};

export type ScenarioGenerateResult = {
  status: Record<string, string>;
  validation?: string | null;
  characters?: ScenarioCharactersFile | null;
  events?: ScenarioEvent[] | null;
  seed_events?: ScenarioEvent[] | null;
};

export type ScenarioChange = { tool: string; result: string };

export type ScenarioChatResult = {
  reply: string;
  changes: ScenarioChange[];
  scenario: ScenarioFull;
  validation?: string | null;
};

export type ExtractionData = {
  turn: number;
  year: number;
  period: number;
  exists: boolean;
  narrative?: string;
  extractor_output?: any;
};

export type HistoryTurnItem = {
  turn: number;
  year: number;
  period: number;
  has_report: boolean;
  has_extraction: boolean;
  has_directive: boolean;
};

export type HistoryDirective = {
  id: number;
  turn: number;
  year: number;
  period: number;
  event_id: string;
  event_title: string;
  actor: string;
  skill_id: string;
  text: string;
  source: string;
  status: string;
  notes: string;
  created_at: string;
  updated_at: string;
};

export type HistoryDetail = {
  turn: number;
  exists: boolean;
  year: number;
  period: number;
  report: string;
  decree_text: string;
  directives: HistoryDirective[];
  extraction: ExtractionData | null;
};

export type TerrainTransform = { x: number; y: number; width: number; height: number };
