const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8010'

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_CINEFORGE_API_BASE_URL)?.replace(/\/$/, '') ??
  DEFAULT_API_BASE_URL

export type Project = {
  id: string
  name: string
  description: string | null
  created_at: string
  persistence: string
}

export type ProjectWorkspaceCreatePayload = {
  idempotency_key: string
  name: string
  auto_title?: boolean
  description?: string | null
  source_mode: 'story' | 'blank' | 'import'
  story_title: string
  base_story: string
  target_duration_sec: number
  audience?: string | null
  genre?: string | null
  tone?: string | null
  point_of_view?: string | null
  visual_style?: string | null
  production_notes?: string | null
  language?: string
  narration_dialogue_preference?: string | null
  source_fidelity_constraints?: string | null
  content_constraints?: string | null
  requested_chapter_count?: number
  chapter_intake?: Array<{
    order_index: number
    title: string
    summary?: string | null
    source_prompt?: string | null
    target_duration_sec?: number | null
    narrative_purpose?: string | null
    dramatic_progression?: string | null
    production_notes?: string | null
  }>
  bootstrap_phase_plan?: boolean
  auto_approve_phases_through?: number | null
  run_phase_one?: boolean
  comparison_baseline?: 'transfiguration_phase_one' | null
  aspect_ratio: string
  preview_width: number
  preview_height: number
  final_width: number
  final_height: number
  fps: number
  captions_enabled: boolean
  audio_enabled: boolean
  production_profile_key?: 'ltx_base@1' | 'wan_base@1'
  stitch_stage?: 'phase7_before_audio' | 'phase8_before_foley'
  speaking_rate: number
  prefer_hosted_providers: boolean
  prefer_local_providers: boolean
  allow_model_download: boolean
  allow_rendering: boolean
  require_production_plan_approval: boolean
  orchestration_mode: string
  privacy_preference: string
  quality_preference: string
  cost_sensitivity: string
}

export type Campaign = {
  id: string
  project_id: string
  name: string
  target_duration_sec: number | null
  created_at: string
  persistence: string
}

export type Job = {
  id: string
  status: string
  detail: string
  workflow_run_id: string | null
  comfy_prompt_id: string | null
  error_message: string | null
}

export type HealthResponse = Record<string, unknown> & {
  status?: string
}

export type RootStatus = {
  app: string
  status: string
  message: string
  docs_url: string
  frontend_dev_url: string
  generation_enabled: boolean
  prompt_submission_publicly_accessible: boolean
  current_phase: string
}

export type RuntimeStatus = {
  status: string
  environment: string
  current_phase: string
  comfyui: HealthResponse
  comfy_api_runner: HealthResponse
  sulphur: HealthResponse & {
    model_loaded?: boolean
    model_id?: string
    model_file?: string
    quantization?: string
    context_length?: number
    parallel?: number
  }
  object_info: {
    status: string
    available: boolean
    class_count: number | null
    error: string | null
  }
  gpu: HealthResponse
  ffmpeg: HealthResponse
  queue: {
    worker_enabled: boolean
    submission_enabled: boolean
    controlled_submission_enabled: boolean
    public_submission_enabled: boolean
    api_runner_available: boolean
    supported_states: string[]
  }
  disabled_actions: Record<string, string>
  links: {
    comfyui: string
    comfy_api_runner: string
  }
}

export type Story = {
  id: string
  project_id: string
  title: string
  base_story: string
  target_duration_sec: number
  logline: string | null
  synopsis: string | null
  audience?: string | null
  tone?: string | null
  genre?: string | null
  visual_style?: string | null
  point_of_view?: string | null
  production_notes?: string | null
  approval_state: string
  active_storyboard_version_id?: string | null
}

export type Shot = {
  id: string
  order_index: number
  display_label: string
  title: string
  duration_sec: number
  duration_override_reason: string | null
  visual_description: string | null
  story_purpose: string | null
  location: string | null
  continuity_source_type: string
  approval_state: string
  production_status: string
  blocked_reason: string | null
  continuity_source_shot_id: string | null
  starting_image_required: boolean
  starting_image_asset_id: string | null
  narration: string | null
  narration_exception_reason?: string | null
  narration_voice_profile_id?: string | null
  narration_start_offset_sec?: number
  narration_expected_duration_sec?: number | null
  narration_approval_state?: ApprovalState
  prompt_positive?: string | null
  prompt_video?: string | null
  prompt_negative?: string | null
  prompt_continuity_instructions?: string | null
  prompt_style_lock?: string | null
  prompt_provider_profile_id?: string | null
  prompt_provider_model_id?: string | null
  prompt_proposal_id?: string | null
  prompt_approval_state?: ApprovalState
  camera_direction?: string | null
  motion_direction?: string | null
  camera_notes?: string | null
  lighting_notes?: string | null
  technical_notes?: string | null
  characters?: ShotCharacterLink[]
  recommendations?: ShotModelRecommendation[]
}

export type ShotCharacterLink = {
  shot_id?: string
  character_id: string
  role_in_shot: string | null
  order_index: number
  continuity_notes: string | null
}

export type ShotModelRecommendation = {
  id: string
  shot_id?: string
  recommendation_type: string
  generation_model_variant_id: string | null
  workflow_template_id: string | null
  rationale: string | null
  availability_status: string
  benchmark_status: string
  risk_status: string | null
  acknowledged_at: string | null
  approval_state: string
  created_at?: string
  updated_at?: string
}

export type ShotModelRecommendationCreatePayload = {
  recommendation_type: 'generation' | 'workflow' | 'voice' | 'other'
  generation_model_variant_id?: string | null
  workflow_template_id?: string | null
  rationale?: string | null
  availability_status?: string
  benchmark_status?: string
  risk_status?: string | null
  approval_state?: ApprovalState
}

export type ShotModelRecommendationUpdatePayload = Partial<ShotModelRecommendationCreatePayload> & {
  acknowledge?: boolean
}

export type Scene = {
  id: string
  order_index: number
  title: string
  summary: string | null
  duration_sec: number
  art_direction_reference_asset_ids?: string[]
  shots: Shot[]
}

export type Chapter = {
  id: string
  order_index: number
  title: string
  summary: string | null
  narrative_purpose?: string | null
  target_duration_sec?: number | null
  dramatic_progression?: string | null
  duration_sec: number
  scenes: Scene[]
}

export type Character = {
  id: string
  story_id?: string
  name: string
  role: string | null
  approval_state: string
  physical_description?: string | null
  age_range?: string | null
  personality?: string | null
  speaking_style?: string | null
  wardrobe?: string | null
  consistency_prompt?: string | null
  negative_identity_prompt?: string | null
  identity_method?: string | null
  assigned_voice_profile_id?: string | null
  reference_assets?: CharacterReferenceSummary[]
}

export type CharacterReferenceSummary = {
  id: string
  asset_id: string
  reference_role: string
  approved: boolean
  order_index: number
}

/** Exact eight server-supported Phase 1 voice setup modes. */
export const VOICE_SETUP_MODES = [
  'placeholder',
  'manual',
  'existing_provider_voice',
  'qwen_voice_design',
  'qwen_custom_voice',
  'elevenlabs_voice_design',
  'parler_local_voice_design',
  'user_provided_consented',
] as const

export type VoiceSetupMode = (typeof VOICE_SETUP_MODES)[number]

export const VOICE_SETUP_MODE_LABELS: Record<VoiceSetupMode, string> = {
  placeholder: 'Placeholder',
  manual: 'Manual profile',
  existing_provider_voice: 'Existing provider voice',
  qwen_voice_design: 'Qwen voice design',
  qwen_custom_voice: 'Qwen preset custom voice',
  elevenlabs_voice_design: 'ElevenLabs voice design',
  parler_local_voice_design: 'Local Parler voice design',
  user_provided_consented: 'User-provided, consented',
}

export type Voice = {
  id: string
  story_id?: string
  character_id?: string | null
  name: string
  setup_mode: VoiceSetupMode | string
  source_type: string
  consent_confirmed: boolean
  approval_state: string
  consent_required: boolean
  language?: string | null
  usage_notes?: string | null
  source_description?: string | null
  design_description?: string | null
  provider?: string | null
  provider_voice_reference?: string | null
  provider_model_id?: string | null
  provider_configuration_status?: string | null
  recipe_name?: string | null
  recipe_description?: string | null
  design_metadata_json?: Record<string, unknown>
  preview_text?: string | null
  accent?: string | null
  presentation?: string | null
  gender_presentation?: string | null
  tone?: string | null
  style?: string | null
  pitch?: string | null
  pacing?: string | null
  energy?: string | null
  speaking_directions?: string | null
  pronunciation_notes?: string | null
  source_asset_id?: string | null
  selected_preview_asset_id?: string | null
  consent_notes?: string | null
  created_at?: string
  updated_at?: string
}

export type StoryboardAggregate = {
  revision: string
  content_hash: string
  planned_duration_sec: number
  discrepancy_sec: number
  story: Story
  chapters: Chapter[]
  characters: Character[]
  voices: Voice[]
}

export type ReadinessReason = {
  code: string
  message: string
  entity_id: string | null
  blocking: boolean
}

export type Readiness = {
  ready: boolean
  planned_duration_sec: number
  target_duration_sec: number
  discrepancy_sec: number
  reasons: ReadinessReason[]
}

export type PhaseANarration = {
  id: string
  voice_profile_id: string | null
  narration_text: string | null
  start_offset_sec: number
  expected_duration_sec: number | null
  narration_exception_reason: string | null
  approval_state: ApprovalState
}

export type PhaseAPromptPackage = {
  id: string
  version: number
  image_prompt: string | null
  video_prompt: string | null
  negative_prompt: string | null
  continuity_instructions: string | null
  style_lock_prompt: string | null
  provider_profile_id: string | null
  provider_model_id: string | null
  proposal_id: string | null
  approval_state: ApprovalState
}

export type PhaseAShot = {
  id: string
  order_index: number
  title: string
  duration_sec: number
  duration_override_reason: string | null
  story_purpose: string | null
  visual_description: string | null
  location: string | null
  camera_direction?: string | null
  motion_direction?: string | null
  continuity_source_type: string
  continuity_source_shot_id: string | null
  starting_image_required: boolean
  starting_image_asset_id: string | null
  approval_state: string
  production_status: string
  blocked_reason: string | null
  narration: PhaseANarration | null
  prompt_packages: PhaseAPromptPackage[]
  characters?: ShotCharacterLink[]
  recommendations?: ShotModelRecommendation[]
}

export type PhaseAScene = {
  id: string
  order_index: number
  title: string
  summary: string | null
  duration_sec: number
  art_direction_reference_asset_ids?: string[]
  shots: PhaseAShot[]
}

export type PhaseAChapter = {
  id: string
  order_index: number
  title: string
  summary: string | null
  duration_sec: number
  scenes: PhaseAScene[]
}

export type PhaseASnapshot = {
  revision: string
  content_hash: string
  planned_duration_sec: number
  target_duration_sec: number
  discrepancy_sec: number
  story: Story
  readiness: Readiness
  chapters: PhaseAChapter[]
  characters: Character[]
  voices: Voice[]
  active_storyboard_version_id: string | null
}

export function normalizePhaseASnapshot(snapshot: PhaseASnapshot): StoryboardAggregate {
  return {
    revision: snapshot.revision,
    content_hash: snapshot.content_hash,
    planned_duration_sec: snapshot.planned_duration_sec,
    discrepancy_sec: snapshot.discrepancy_sec,
    story: snapshot.story,
    chapters: snapshot.chapters.map((chapter) => ({
      ...chapter,
      scenes: chapter.scenes.map((scene) => ({
        ...scene,
        shots: scene.shots.map((shot) => {
          const prompt = shot.prompt_packages.at(-1)
          return {
            ...shot,
            display_label:
              shot.order_index < 26 ? String.fromCharCode(65 + shot.order_index) : String(shot.order_index + 1),
            narration: shot.narration?.narration_text ?? null,
            narration_exception_reason: shot.narration?.narration_exception_reason ?? null,
            narration_voice_profile_id: shot.narration?.voice_profile_id ?? null,
            narration_start_offset_sec: shot.narration?.start_offset_sec ?? 0,
            narration_expected_duration_sec: shot.narration?.expected_duration_sec ?? null,
            narration_approval_state: shot.narration?.approval_state ?? 'draft',
            prompt_positive: prompt?.image_prompt ?? null,
            prompt_video: prompt?.video_prompt ?? null,
            prompt_negative: prompt?.negative_prompt ?? null,
            prompt_continuity_instructions: prompt?.continuity_instructions ?? null,
            prompt_style_lock: prompt?.style_lock_prompt ?? null,
            prompt_provider_profile_id: prompt?.provider_profile_id ?? null,
            prompt_provider_model_id: prompt?.provider_model_id ?? null,
            prompt_proposal_id: prompt?.proposal_id ?? null,
            prompt_approval_state: prompt?.approval_state ?? 'draft',
            camera_direction: shot.camera_direction ?? null,
            motion_direction: shot.motion_direction ?? null,
            camera_notes: shot.camera_direction ?? null,
            lighting_notes: null,
            technical_notes: shot.motion_direction ?? null,
          }
        }),
      })),
    })),
    characters: snapshot.characters,
    voices: snapshot.voices,
  }
}

export type ActivePlanningMediaAssetApprovalState = 'draft' | 'in_review' | 'approved' | 'blocked'
export type PlanningMediaAssetApprovalState = ActivePlanningMediaAssetApprovalState | 'archived'

export type PlanningMediaAsset = {
  id: string
  project_id: string
  kind: string
  source_type: string
  managed_uri: string
  sha256: string | null
  mime_type: string | null
  width: number | null
  height: number | null
  duration_sec: number | null
  approval_state: PlanningMediaAssetApprovalState
  metadata_json: Record<string, unknown>
  original_filename: string | null
  size_bytes: number | null
  archived_at: string | null
  created_at: string
  updated_at: string
  is_duplicate: boolean
}

export type PlanningMediaAssetList = {
  items: PlanningMediaAsset[]
  total: number
}

export type PlanningMediaAssetUpload = {
  asset: PlanningMediaAsset
  created: boolean
  duplicate_of_existing: boolean
}

export type StartingImageApprovalUpdate = {
  approval_state: ActivePlanningMediaAssetApprovalState
  expected_approval_state: ActivePlanningMediaAssetApprovalState
  reason?: string | null
  changed_by?: string | null
}

export type CharacterReferenceLink = {
  id: string
  character_id: string
  asset_id: string
  reference_role: 'primary' | 'alternate' | 'expression' | 'costume' | 'detail' | string
  approved: boolean
  order_index: number
  created_at: string
  updated_at: string
  asset: PlanningMediaAsset | null
}

export type RuntimeCatalogModel = {
  id: string
  family: string
  name: string
  source_url: string | null
  license: string | null
  evidence_level: string
  notes: string | null
  registration_status: string
  variant_count: number
}

export type RuntimeCatalogModelVariant = {
  id: string
  model_id: string
  variant_name: string
  params_b: number | null
  precision: string | null
  quantization: string | null
  compatible_24gb_status: string
  notes: string | null
  native_voice_capability: string
  native_voice_capability_source: string | null
  path_status: string
  checksum_status: string
  has_file_path_recorded: boolean
  has_sha256_recorded: boolean
  has_file_size_recorded: boolean
  file_size_bytes: number | null
  benchmark_status: string
  benchmark_run_count: number
  claims: Record<string, boolean>
}

export type RuntimeCatalogWorkflowTemplate = {
  id: string
  name: string
  version: string
  sha256: string
  comfyui_commit: string | null
  created_at: string
  registration_status: string
  has_manifest: boolean
  has_workflow_api: boolean
  benchmark_status: string
  benchmark_run_count: number
  claims: Record<string, boolean>
}

export type RuntimeCatalogSummary = {
  models: number
  model_variants: number
  workflow_templates: number
  quantizations: number
  loras: number
  benchmark_runs: number
  evidence_note: string
}

export type RuntimeCatalog = {
  summary: RuntimeCatalogSummary
  models: RuntimeCatalogModel[]
  model_variants: RuntimeCatalogModelVariant[]
  workflow_templates: RuntimeCatalogWorkflowTemplate[]
  quantizations: unknown[]
  loras: unknown[]
}

export type LocalModelInventory = {
  status: 'available' | 'partial' | 'unavailable' | string
  source_url: string
  total_count: number
  categories: Record<string, string[]>
  errors: Record<string, string>
}

export type ProviderExecutionMode = 'disabled' | 'manual' | 'assisted' | 'automatic'

export type ProviderProfile = {
  id: string
  provider_identifier: string
  display_name: string
  provider_model_id: string | null
  execution_mode: ProviderExecutionMode | string
  availability_status: string
  privacy_classification: string | null
  capabilities_json: Record<string, unknown>
  configuration_reference: string | null
  capabilities_checked_at: string | null
  health_checked_at: string | null
  capability_source: string | null
  created_at: string
  updated_at: string
}

export type ProviderProfileCreatePayload = {
  provider_identifier: string
  display_name: string
  provider_model_id?: string | null
  execution_mode: ProviderExecutionMode
  availability_status?: string
  privacy_classification?: string | null
  capabilities_json?: Record<string, unknown>
  configuration_reference?: string | null
  capability_source?: string | null
}

export type ProviderCatalogEntry = {
  provider_identifier: string
  display_name: string
  availability_status: string
  execution_mode: string
  privacy_classification: string
  capabilities: string[]
  capability_source: string
  checked_at: string
  connection_test_supported: boolean
  detail: string
}

export type ProviderCatalogResponse = {
  schema_name: string
  generated_at: string
  providers: ProviderCatalogEntry[]
}

export type ProviderConnectionTestResponse = {
  provider_identifier: string
  attempted: boolean
  success: boolean
  availability_status: string
  checked_at: string
  latency_ms: number | null
  capabilities: string[]
  detail: string
  error_code: string | null
}

export type ProviderCapabilitiesResponse = {
  provider_identifier: string
  availability_status: string
  capabilities: string[]
  capability_source: string
  checked_at: string
}

export type ProviderProfileCapabilitiesResponse = {
  profile_id: string
  provider_identifier: string
  declared_capabilities: string[]
  declaration_source: string | null
  verified_capabilities: string[]
  verified_capability_source: string
  verified_availability_status: string
  checked_at: string
}

export type RoutingValidationIssue = {
  code: string
  message: string
  task_type: string | null
  provider_identifier: string | null
}

export type RoutingPreflightRoute = {
  task_type: PlanningTaskType
  source: string
  provider_identifier: string | null
  logical_model: string | null
  resolved_model: string | null
  availability_status: string | null
  privacy_classification: string | null
}

export type RoutingPreflightPayload = {
  routing_mode: OrchestrationRoutingMode
  manual_routes?: ManualTaskRoute[]
  prefer_local_providers: boolean
  prefer_hosted_providers: boolean
  max_steps?: number
  transport_retry_limit?: number
  time_budget_sec?: number
  task_types?: PlanningTaskType[] | null
}

export type RoutingPreflightResponse = {
  story_id: string
  valid: boolean
  requested_mode: OrchestrationRoutingMode
  effective_mode: OrchestrationRoutingMode
  routes: RoutingPreflightRoute[]
  provider_facts: ProviderCatalogEntry[]
  errors: RoutingValidationIssue[]
  warnings: RoutingValidationIssue[]
  metadata: Record<string, unknown>
}

export type TaskProviderAssignment = {
  id: string
  story_id: string
  task_type: PlanningTaskType
  provider_profile_id: string
  assignment_mode: 'manual' | 'default' | 'suggested' | string
  rationale: string | null
  priority: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export type TaskProviderAssignmentPayload = {
  task_type: PlanningTaskType
  provider_profile_id: string
  assignment_mode: 'manual' | 'default' | 'suggested'
  rationale?: string | null
  priority?: number
  enabled?: boolean
}

export type ProjectStoryboardSettings = {
  id: string | null
  project_id: string
  settings_version: number
  shot_duration_min_sec: number
  shot_duration_max_sec: number
  continuity_policy_json: Record<string, unknown>
  prompting_policy_json: Record<string, unknown>
  voice_policy_json: Record<string, unknown>
  approval_policy_json: Record<string, unknown>
  speaking_rate: number
  aspect_ratio: string
  preview_width: number
  preview_height: number
  final_width: number
  final_height: number
  fps: number
  captions_enabled: boolean
  audio_enabled: boolean
  production_profile_key: 'ltx_base@1' | 'wan_base@1'
  production_profile_snapshot_json: Record<string, unknown>
  stitch_stage: 'phase7_before_audio' | 'phase8_before_foley'
  prefer_hosted_providers: boolean
  prefer_local_providers: boolean
  allow_model_download: boolean
  allow_rendering: boolean
  require_voice_consent: boolean
  require_production_plan_approval: boolean
}

export type ProjectStoryboardSettingsUpdate = Omit<
  ProjectStoryboardSettings,
  'id' | 'project_id' | 'settings_version'
> & {
  expected_settings_version?: number
}

export type ProjectWorkspace = {
  project: Project
  story: Story
  settings: ProjectStoryboardSettings
  idempotent_replay: boolean
  production_pipeline: ProductionPipeline | null
}

export type SulphurProjectWorkspace = ProjectWorkspace & {
  intake_provider: 'sulphur'
  intake_model: string
  source_prompt_preserved: true
  target_duration_sec: number
  planned_scene_count: number
  nominal_scene_duration_sec: 8
  clip_duration_range_sec: [6, 10]
}

export type ComfyRestartRequest = {
  restart_id: string
  status: string
  message: string
}

export type ComfyRestartStatus = ComfyRestartRequest & {
  complete: boolean
  failed: boolean
}

export type PhaseLifecycleState =
  | 'not_started'
  | 'drafting'
  | 'qa_pending'
  | 'needs_revision'
  | 'ready_for_review'
  | 'approved'
  | 'blocked'

export type PhaseOneDurationAnalysis = {
  target_duration_sec: number
  narration_word_count: number
  dialogue_word_count: number
  narration_duration_sec: number
  dialogue_duration_sec: number
  planned_silence_visual_duration_sec: number
  estimated_total_duration_sec: number
  narration_wpm?: number
  dialogue_wpm?: number
}

export type PhaseOnePackage = {
  schema_name: string
  schema_version: number
  project_title: string
  logline: string
  short_synopsis: string
  detailed_treatment: string
  complete_script: string
  narration_script: string
  dialogue_script: string
  non_dialogue_action: string[]
  silent_visual_beats: string[]
  emotional_progression: string[]
  dramatic_escalation: string[]
  narrative_structure: Record<'opening' | 'middle' | 'climax' | 'resolution', string>
  pacing_plan: Array<Record<string, string | number>>
  planned_scene_count?: number
  nominal_scene_duration_sec?: number
  clip_duration_range_sec?: [number, number]
  scene_duration_plan_sec?: number[]
  duration_analysis: PhaseOneDurationAnalysis
  script_word_count: number
  source_fidelity_notes: string[]
  creative_assumptions: string[]
  creative_direction: Record<string, string | null>
  generation_boundary: {
    phase: 1
    text_only: true
    media_generated: false
    rendering_enabled: false
    final_scene_or_shot_segmentation_created: false
  }
  baseline_comparison?: {
    baseline_key: string
    baseline_project_id: string
    classification: string
    differences: Array<{ item: string; classification: string; detail: string }>
    missing_count: number
    unsafe_count: number
    review_items: string[]
    note: string
  }
}

export type PhaseOneGenerationPayload = {
  original_prompt: string
  target_duration_sec: number
  audience?: string | null
  genre?: string | null
  tone?: string | null
  language?: string
  visual_style?: string | null
  narration_dialogue_preference?: string | null
  source_fidelity_constraints?: string | null
  content_constraints?: string | null
  requested_chapter_count?: number
  chapter_intake?: Record<string, unknown>[]
  comparison_baseline?: string | null
  requested_by?: string | null
}

export type ProductionQAReport = {
  id: string
  entity_type: string
  entity_id: string
  created_at: string
  report_json: {
    phase_number: number
    passed: boolean
    result: 'pass' | 'fail'
    checks: Array<{ code: string; label: string; passed: boolean; blocking: boolean; detail: string }>
    blocking_failures: Array<Record<string, unknown>>
    review_items: string[]
    baseline_comparison?: PhaseOnePackage['baseline_comparison']
    phase_boundary: Record<string, boolean>
  }
}

export type PhaseVersionSource = 'baseline' | 'manual' | 'generated' | 'revision' | 'imported'

export type ProductionPhaseVersion = {
  id: string
  version_number: number
  label?: string
  notes?: string
  source?: PhaseVersionSource
  snapshot_schema_version?: number
  lifecycle_state: PhaseLifecycleState
  completed: boolean
  input_snapshot_json: Record<string, unknown>
  output_json: PhaseOnePackage | Record<string, unknown>
  input_hash: string
  output_hash: string
  created_by: string | null
  previous_version_id: string | null
  created_at: string
  updated_at: string
  verified?: boolean
}

export type PhaseVersionSummary = {
  id: string
  version_number: number
  label: string
  notes: string
  source: PhaseVersionSource
  lifecycle_state: PhaseLifecycleState
  completed: boolean
  snapshot_schema_version: number
  input_hash: string
  output_hash: string
  created_by: string | null
  previous_version_id: string | null
  created_at: string
  updated_at: string
}

export type PhaseVersionDetail = ProductionPhaseVersion & {
  story_id: string
  project_id: string
  phase_number: number
  phase_name: string
  verified: boolean
}

export type PhaseHistoryExport = {
  schema_name: 'cineforge.phase-history'
  version: 1
  project_id: string
  story_id: string
  exported_at: string
  integrity: {
    verified: true
    iteration_count: number
    snapshot_count: number
    phase_counts: Record<string, number>
    hashes: string[]
  }
  iterations: PhaseVersionDetail[]
}

export type ProductionPhase = {
  id: string
  phase_number: number
  name: string
  lifecycle_state: PhaseLifecycleState
  current_version_number: number | null
  version_count?: number
  is_locked: boolean
  locked_reason: string | null
  is_stale: boolean
  stale_reason: string | null
  generation_completed_at: string | null
  approved_at: string | null
  latest_version: ProductionPhaseVersion | null
  latest_qa_report: ProductionQAReport | null
}

export type ProductionPipeline = {
  story_id: string
  project_id: string
  exact_phase_count: 8
  phases: ProductionPhase[]
  completion_message: string | null
}

export type PhaseVersionCreateResponse = {
  version: PhaseVersionDetail
  pipeline: ProductionPipeline
}

export type PhaseOneRevisionPayload = Pick<
  PhaseOnePackage,
  | 'project_title'
  | 'logline'
  | 'short_synopsis'
  | 'detailed_treatment'
  | 'complete_script'
  | 'narration_script'
  | 'dialogue_script'
  | 'non_dialogue_action'
  | 'silent_visual_beats'
  | 'emotional_progression'
  | 'dramatic_escalation'
  | 'source_fidelity_notes'
  | 'creative_assumptions'
> & {
  expected_version_number: number
  requested_by?: string | null
}

export type PhaseOneMutationResponse = {
  pipeline: ProductionPipeline
  phase: ProductionPhase
  completion_message: string
}

export type PhaseApproveResponse = {
  pipeline: ProductionPipeline
  phase: ProductionPhase
  message: string
}

export type PhaseSixImageStatus = {
  shot_count: number
  required_count: number
  assigned_count: number
  approved_count: number
  in_review_count: number
  missing_count: number
  complete: boolean
  phase_7_locked: boolean | null
  runtime_reachable: boolean | null
}

export type PhaseSixImagePrepareResponse = {
  status: PhaseSixImageStatus
  message: string
}

export type StartingImageGenerateRequest = {
  requested_by?: string
  seed?: number | null
  model_name?: string | null
  workflow_template_id?: string | null
  workflow_label?: string | null
  workflow_source?: string | null
  workflow_api_json?: Record<string, unknown> | null
}

export type StartingImageGenerateResponse = {
  asset: PlanningMediaAsset
  created: boolean
  duplicate_of_existing: boolean
  shot_id: string
  previous_asset_id: string | null
  status: PhaseSixImageStatus
  prompt_id: string | null
  model_name: string
  seed: number
}

export type VoiceProfileCreatePayload = {
  name: string
  setup_mode: VoiceSetupMode
  character_id?: string | null
  language?: string
  provider?: string
  provider_voice_reference?: string
  design_description?: string
  custom_voice_speaker?: string
  source_asset_id?: string | null
  source_description?: string
  usage_notes?: string
  consent_notes?: string
  consent_required: boolean
  consent_confirmed: boolean
}

export type VoiceProfileUpdatePayload = Omit<
  Partial<VoiceProfileCreatePayload>,
  'language' | 'usage_notes' | 'source_description'
> & {
  language?: string | null
  usage_notes?: string | null
  source_description?: string | null
  provider_model_id?: string | null
  recipe_name?: string | null
  recipe_description?: string | null
  preview_text?: string | null
  accent?: string | null
  presentation?: string | null
  gender_presentation?: string | null
  tone?: string | null
  style?: string | null
  pitch?: string | null
  pacing?: string | null
  energy?: string | null
  speaking_directions?: string | null
  pronunciation_notes?: string | null
  design_metadata?: Record<string, unknown>
}

export type VoiceRecipe = {
  id: string
  voice_profile_id: string
  provider: string
  model: string | null
  recipe_name: string | null
  description: string | null
  seed: number | null
  design_metadata_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type VoiceRecipeCreatePayload = {
  provider: string
  model?: string | null
  recipe_name?: string | null
  description?: string | null
  seed?: number | null
  design_metadata?: Record<string, unknown>
}

export type VoicePreview = {
  id: string
  voice_profile_id: string
  voice_recipe_id: string | null
  planning_media_asset_id: string | null
  provider: string | null
  model: string | null
  preview_text: string | null
  selected: boolean
  rejected: boolean
  created_at: string
  updated_at: string
}

export type VoiceApproveResult = {
  voice_profile_id: string
  approval_state: string
  approved_by: string
  preview_required: boolean
  preview_present: boolean
  warnings: string[]
}

export type VoicePreviewJob = {
  job_id: string
  voice_profile_id: string
  status: 'pending' | 'reserved' | 'running' | 'complete' | 'failed' | 'canceled'
  provider: string | null
  model: string | null
  preview_id: string | null
  planning_media_asset_id: string | null
  error_message: string | null
  message: string | null
}

export type ShotUpdatePayload = {
  order_index: number
  title: string
  duration_sec: number
  duration_override_reason?: string | null
  story_purpose?: string | null
  visual_description?: string | null
  location?: string | null
  camera_direction?: string | null
  motion_direction?: string | null
  continuity_source_type: string
  continuity_source_shot_id?: string | null
  starting_image_required: boolean
  starting_image_asset_id?: string | null
}

export type ShotPatchPayload = Partial<ShotUpdatePayload> & {
  camera_direction?: string | null
  motion_direction?: string | null
  approval_state?: ApprovalState
  production_status?: string
  blocked_reason?: string | null
}

export type ApprovalState = 'draft' | 'in_review' | 'approved' | 'blocked'

export type ShotNarrationPayload = {
  voice_profile_id: string | null
  narration_text: string | null
  start_offset_sec: number
  expected_duration_sec: number | null
  narration_exception_reason: string | null
  approval_state: ApprovalState
}

export type ShotNarrationRecord = ShotNarrationPayload & {
  id: string
  shot_id: string
  created_at: string
  updated_at: string
}

export type ShotPromptPackagePayload = {
  image_prompt: string | null
  video_prompt: string | null
  negative_prompt: string | null
  continuity_instructions: string | null
  style_lock_prompt: string | null
  provider_profile_id: string | null
  provider_model_id: string | null
  proposal_id: string | null
  approval_state: ApprovalState
}

export type ShotPromptPackageRecord = ShotPromptPackagePayload & {
  id: string
  shot_id: string
  version: number
  created_at: string
  updated_at: string
}

export type OrchestrationRoutingMode = 'automatic' | 'manual' | 'hybrid'

export type PlanningTaskType =
  | 'story_structure'
  | 'character_bible'
  | 'chapter_outline'
  | 'scene_breakdown'
  | 'shot_list'
  | 'narration_plan'
  | 'prompt_package'
  | 'continuity_plan'
  | 'model_recommendation'
  | 'production_proposal'

export type ManualTaskRoute = {
  task_type: PlanningTaskType
  provider_identifier: string
  logical_model?: 'luna' | 'terra' | 'sol' | null
  resolved_model?: string | null
  rationale?: string | null
}

export type CreateOrchestrationRunPayload = {
  story_id: string
  base_storyboard_version_id?: string | null
  requested_by?: string | null
  routing_mode: OrchestrationRoutingMode
  manual_routes?: ManualTaskRoute[]
  prefer_local_providers: boolean
  prefer_hosted_providers: boolean
  max_steps?: number
  repair_budget?: number
  time_budget_sec?: number
  transport_retry_limit?: number
  idempotency_key?: string | null
  task_types?: PlanningTaskType[] | null
}

export type OrchestrationRun = {
  id: string
  story_id: string
  base_storyboard_version_id: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'canceled' | string
  requested_by: string | null
  routing_snapshot_json: Record<string, unknown>
  default_provider_snapshot_json: Record<string, unknown>
  target_duration_sec_snapshot: number | null
  input_hash: string | null
  current_step: number
  max_steps: number
  repair_budget: number
  repair_used: number
  started_at: string | null
  completed_at: string | null
  failed_at: string | null
  canceled_at: string | null
  failure_category: string | null
  failure_message: string | null
  created_at: string
  updated_at: string
}

export type OrchestrationStep = {
  id: string
  run_id: string
  sequence_index: number
  task_type: string
  status: string
  provider_identifier: string | null
  logical_model: string | null
  resolved_model: string | null
  attempt_number: number
  input_hash: string | null
  output_hash: string | null
  proposal_id: string | null
  started_at: string | null
  completed_at: string | null
  error_category: string | null
  error_message: string | null
  metadata_json: Record<string, unknown>
}

export type OrchestrationEvent = {
  id: string
  run_id: string
  step_id: string | null
  event_type: string
  actor_type: string
  actor_reference: string | null
  details_json: Record<string, unknown>
  created_at: string
}

export type ProviderInvocation = {
  id: string
  run_id: string
  step_id: string | null
  provider_identifier: string
  model: string | null
  idempotency_key: string
  request_hash: string | null
  response_hash: string | null
  latency_ms: number | null
  usage_json: Record<string, unknown>
  status: string
  provider_request_id: string | null
  finish_category: string | null
  error_category: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type ProposalSummary = {
  id: string
  proposal_type: string
  status: string
  schema_name: string | null
  content_hash: string | null
  validation_status: string | null
  story_id: string | null
  orchestration_run_id: string | null
  created_at: string
}

export type OrchestrationRunDetail = OrchestrationRun & {
  steps: OrchestrationStep[]
  events: OrchestrationEvent[]
  invocations: ProviderInvocation[]
  proposals: ProposalSummary[]
}

export type CreateOrchestrationRunResponse = {
  run: OrchestrationRun
  created: boolean
  idempotent_replay: boolean
}

export type OrchestrationRunActionResponse = {
  run: OrchestrationRun
  message: string
}

export type StoryboardProposal = {
  id: string
  proposal_type: string
  payload: Record<string, unknown>
  status: string
  validation_errors: unknown[]
  story_id: string | null
  orchestration_run_id: string | null
  base_storyboard_version_id: string | null
  schema_name: string | null
  content_hash: string | null
  validation_status: string | null
  validation_report_json: Record<string, unknown>
  warnings_json: unknown[]
  reviewed_by: string | null
  reviewed_at: string | null
  applied_at: string | null
  rejected_at: string | null
  rejection_reason: string | null
  created_at: string | null
}

export type ProposalDiffOperation = {
  op: string
  path: string
  before: unknown
  after: unknown
}

export type ProposalDiff = {
  proposal_id: string
  base_storyboard_version_id: string | null
  base_content_hash: string | null
  proposed_content_hash: string
  ops: ProposalDiffOperation[]
}

export type ProposalApplyResult = {
  proposal_id: string
  story_id: string
  new_storyboard_version_id: string
  version_number: number
  content_hash: string
  status: string
}

export type ExportLinks = {
  json_url: string
  shot_list_csv_url: string
  pdf_available: boolean
  edl_available: boolean
  render_package_available: boolean
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(formatApiError(status, detail))
    this.status = status
    this.detail = detail
  }
}

function formatApiError(status: number, detail: unknown): string {
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return JSON.stringify(item)
      })
      .join(', ')
  }

  if (detail && typeof detail === 'object' && 'detail' in detail) {
    return formatApiError(status, (detail as { detail: unknown }).detail)
  }

  return `Request failed with status ${status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    const headers = new Headers(init?.headers)
    if (init?.body != null && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    })
  } catch (error) {
    throw new Error(
      `Backend unreachable at ${API_BASE_URL}. Start FastAPI or update VITE_CINEFORGE_API_BASE_URL. ${
        error instanceof Error ? error.message : ''
      }`,
      { cause: error },
    )
  }

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, body)
  }

  return body as T
}

/** Soft GET helper: returns null for 404/405/501 so pages can show truthful unavailable states. */
async function optionalRequest<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    return await request<T>(path, init)
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 405 || error.status === 501)) {
      return null
    }
    throw error
  }
}

export function exportJsonUrl(storyId: string): string {
  return `${API_BASE_URL}/storyboard/stories/${storyId}/export.json`
}

export function exportShotListCsvUrl(storyId: string): string {
  return `${API_BASE_URL}/storyboard/stories/${storyId}/shot-list.csv`
}

export function planningAssetContentUrl(assetId: string): string {
  return `${API_BASE_URL}/assets/${assetId}/content`
}

export const api = {
  rootStatus: () => request<RootStatus>('/'),
  health: () => request<HealthResponse>('/health'),
  comfyHealth: () => request<HealthResponse>('/health/comfy'),
  comfyApiRunnerHealth: () => request<HealthResponse>('/health/comfy-api-runner'),
  sulphurHealth: () => request<HealthResponse>('/health/sulphur'),
  gpuHealth: () => request<HealthResponse>('/health/gpu'),
  ffmpegHealth: () => request<HealthResponse>('/health/ffmpeg'),
  runtimeStatus: () => request<RuntimeStatus>('/runtime/status'),
  restartComfyUi: () =>
    request<ComfyRestartRequest>('/runtime/comfyui/restart', { method: 'POST' }),
  comfyRestartStatus: (restartId: string) =>
    request<ComfyRestartStatus>(`/runtime/comfyui/restart/${encodeURIComponent(restartId)}`),

  listProjects: () => request<Project[]>('/projects'),
  createProject: (payload: { name: string; description?: string | null }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  createProjectWorkspace: (payload: ProjectWorkspaceCreatePayload) =>
    request<ProjectWorkspace>('/projects/workspace', { method: 'POST', body: JSON.stringify(payload) }),
  createProjectFromSulphur: (payload: { idempotency_key: string; prompt: string }) =>
    request<SulphurProjectWorkspace>('/projects/sulphur-intake', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getProject: (projectId: string) => request<Project>(`/projects/${projectId}`),
  getProductionPipeline: (storyId: string) =>
    request<ProductionPipeline>(`/production/stories/${storyId}`),
  generatePhaseOne: (storyId: string, payload: PhaseOneGenerationPayload) =>
    request<PhaseOneMutationResponse>(`/production/stories/${storyId}/phases/1/generate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  approveProductionPhase: (
    storyId: string,
    phaseNumber: number,
    payload: { approved_by: string; notes?: string | null },
  ) =>
    request<PhaseApproveResponse>(
      `/production/stories/${storyId}/phases/${phaseNumber}/approve`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  getPhaseSixImageStatus: (storyId: string) =>
    request<PhaseSixImageStatus>(`/production/stories/${storyId}/phase6/images/status`),
  preparePhaseSixImages: (storyId: string, requestedBy = 'CineForge QA') =>
    request<PhaseSixImagePrepareResponse>(`/production/stories/${storyId}/phase6/images/prepare`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: requestedBy, notes: 'Phase 6 planning-image completion required.' }),
    }),
  generateStartingImage: (
    storyId: string,
    shotId: string,
    payload: StartingImageGenerateRequest = {},
  ) =>
    request<StartingImageGenerateResponse>(
      `/production/stories/${storyId}/phase6/images/shots/${shotId}/generate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  listPhaseVersions: (storyId: string, phaseNumber: number) =>
    request<PhaseVersionSummary[]>(
      `/production/stories/${storyId}/phases/${phaseNumber}/versions`,
    ),
  getPhaseVersion: (storyId: string, phaseNumber: number, versionId: string) =>
    request<PhaseVersionDetail>(
      `/production/stories/${storyId}/phases/${phaseNumber}/versions/${versionId}`,
    ),
  createPhaseVersion: (
    storyId: string,
    phaseNumber: number,
    payload: { label: string; notes?: string; requested_by?: string | null },
  ) =>
    request<PhaseVersionCreateResponse>(
      `/production/stories/${storyId}/phases/${phaseNumber}/versions`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  exportPhaseHistory: (storyId: string) =>
    request<PhaseHistoryExport>(`/production/stories/${storyId}/versions/export`),
  revisePhaseOne: (storyId: string, payload: PhaseOneRevisionPayload) =>
    request<PhaseOneMutationResponse>(`/production/stories/${storyId}/phases/1`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  listCampaigns: (projectId?: string) =>
    request<Campaign[]>(projectId ? `/campaigns?project_id=${projectId}` : '/campaigns'),
  createCampaign: (payload: {
    project_id: string
    name: string
    target_duration_sec?: number | null
  }) => request<Campaign>('/campaigns', { method: 'POST', body: JSON.stringify(payload) }),
  getCampaign: (campaignId: string) => request<Campaign>(`/campaigns/${campaignId}`),

  listJobs: (limit = 25) => request<Job[]>(`/jobs?limit=${limit}`),
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),

  listStories: (projectId?: string) =>
    request<Story[]>(projectId ? `/storyboard/stories?project_id=${projectId}` : '/storyboard/stories'),
  createStory: (payload: {
    project_id: string
    title: string
    base_story: string
    target_duration_sec: number
  }) => request<Story>('/storyboard/stories', { method: 'POST', body: JSON.stringify(payload) }),
  updateStory: (storyId: string, payload: Record<string, unknown>, expectedRevision: string) =>
    request<Story>(`/storyboard/stories/${storyId}`, {
      method: 'PATCH',
      body: JSON.stringify({ ...payload, expected_revision: expectedRevision }),
    }),
  getStory: (storyId: string) => request<Story>(`/storyboard/stories/${storyId}`),
  aggregate: (storyId: string) => request<StoryboardAggregate>(`/storyboard/stories/${storyId}/aggregate`),
  phaseA: (storyId: string) => request<PhaseASnapshot>(`/storyboard/stories/${storyId}/phase-a`),
  readiness: (storyId: string) => request<Readiness>(`/storyboard/stories/${storyId}/readiness`),

  createOrchestrationRun: (payload: CreateOrchestrationRunPayload) =>
    request<CreateOrchestrationRunResponse>('/orchestration/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listOrchestrationRuns: (storyId: string) =>
    request<OrchestrationRun[]>(`/orchestration/stories/${storyId}/runs`),
  getOrchestrationRun: (runId: string) =>
    request<OrchestrationRunDetail>(`/orchestration/runs/${runId}`),
  startOrchestrationRun: (runId: string) =>
    request<OrchestrationRunActionResponse>(`/orchestration/runs/${runId}/start`, {
      method: 'POST',
    }),
  retryOrchestrationRun: (runId: string, requestedBy?: string) =>
    request<CreateOrchestrationRunResponse>(`/orchestration/runs/${runId}/retry`, {
      method: 'POST',
      body: JSON.stringify({ requested_by: requestedBy?.trim() || null }),
    }),
  cancelOrchestrationRun: (runId: string, reason?: string, requestedBy?: string) =>
    request<OrchestrationRunActionResponse>(`/orchestration/runs/${runId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({
        reason: reason?.trim() || null,
        requested_by: requestedBy?.trim() || null,
      }),
    }),

  listStoryProposals: (storyId: string) =>
    request<StoryboardProposal[]>(`/proposal-review/story/${storyId}`),
  getProposal: (proposalId: string) =>
    request<StoryboardProposal>(`/proposal-review/${proposalId}`),
  getProposalDiff: (proposalId: string) =>
    request<ProposalDiff>(`/proposal-review/${proposalId}/diff`),
  reviewProposal: (proposalId: string, reviewedBy: string, notes?: string) =>
    request<StoryboardProposal>(`/proposal-review/${proposalId}/review`, {
      method: 'POST',
      body: JSON.stringify({ reviewed_by: reviewedBy, notes: notes?.trim() || null }),
    }),
  rejectProposal: (proposalId: string, rejectedBy: string, reason: string) =>
    request<StoryboardProposal>(`/proposal-review/${proposalId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejected_by: rejectedBy, reason }),
    }),
  applyProposal: (
    proposalId: string,
    appliedBy: string,
    expectedBaseVersionId?: string | null,
    expectedBaseContentHash?: string | null,
  ) =>
    request<ProposalApplyResult>(`/proposal-review/${proposalId}/apply`, {
      method: 'POST',
      body: JSON.stringify({
        applied_by: appliedBy,
        expected_base_version_id: expectedBaseVersionId ?? null,
        expected_base_content_hash: expectedBaseContentHash ?? null,
      }),
    }),

  createChapter: (storyId: string, payload: {
    title: string
    summary?: string | null
    order_index: number
    narrative_purpose?: string | null
    target_duration_sec?: number | null
    dramatic_progression?: string | null
  }) =>
    request<Chapter>(`/storyboard/stories/${storyId}/chapters`, { method: 'POST', body: JSON.stringify(payload) }),
  updateChapter: (chapterId: string, payload: Record<string, unknown>) =>
    request(`/storyboard/chapters/${chapterId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteChapter: (chapterId: string, reason?: string) =>
    request<void>(
      `/storyboard/chapters/${chapterId}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'DELETE' },
    ),
  reorderChapters: (storyId: string, orderedIds: string[]) =>
    request<void>(`/storyboard/stories/${storyId}/chapters/reorder`, {
      method: 'POST',
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),
  createScene: (chapterId: string, payload: { title: string; summary?: string; order_index: number }) =>
    request(`/storyboard/chapters/${chapterId}/scenes`, { method: 'POST', body: JSON.stringify(payload) }),
  updateScene: (sceneId: string, payload: Record<string, unknown>) =>
    request(`/storyboard/scenes/${sceneId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteScene: (sceneId: string, reason?: string) =>
    request<void>(
      `/storyboard/scenes/${sceneId}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'DELETE' },
    ),
  reorderScenes: (chapterId: string, orderedIds: string[]) =>
    request<void>(`/storyboard/chapters/${chapterId}/scenes/reorder`, {
      method: 'POST',
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),
  createShot: (
    sceneId: string,
    payload: {
      title: string
      duration_sec: number
      duration_override_reason?: string
      order_index: number
      visual_description?: string
    },
  ) => request(`/storyboard/scenes/${sceneId}/shots`, { method: 'POST', body: JSON.stringify(payload) }),
  updateShot: (shotId: string, payload: ShotUpdatePayload) =>
    request(`/storyboard/shots/${shotId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  patchShot: (shotId: string, payload: ShotPatchPayload) =>
    request<Shot>(`/storyboard/shots/${shotId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  listShotCharacters: (shotId: string) =>
    request<ShotCharacterLink[]>(`/storyboard/shots/${shotId}/characters`),
  replaceShotCharacters: (shotId: string, characters: ShotCharacterLink[]) =>
    request<ShotCharacterLink[]>(`/storyboard/shots/${shotId}/characters`, {
      method: 'PUT',
      body: JSON.stringify({
        characters: characters.map(({ character_id, order_index, role_in_shot, continuity_notes }) => ({
          character_id,
          order_index,
          role_in_shot,
          continuity_notes,
        })),
      }),
    }),

  putShotNarration: (shotId: string, payload: ShotNarrationPayload) =>
    request<ShotNarrationRecord>(`/storyboard-crud/shots/${shotId}/narration`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteShotNarration: (shotId: string) =>
    request<void>(`/storyboard-crud/shots/${shotId}/narration`, { method: 'DELETE' }),
  createShotPromptPackage: (shotId: string, payload: ShotPromptPackagePayload) =>
    request<ShotPromptPackageRecord>(`/storyboard-crud/shots/${shotId}/prompt-packages`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listShotRecommendations: (shotId: string) =>
    request<ShotModelRecommendation[]>(`/storyboard-crud/shots/${shotId}/recommendations`),
  createShotRecommendation: (shotId: string, payload: ShotModelRecommendationCreatePayload) =>
    request<ShotModelRecommendation>(`/storyboard-crud/shots/${shotId}/recommendations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateShotRecommendation: (
    recommendationId: string,
    payload: ShotModelRecommendationUpdatePayload,
  ) =>
    request<ShotModelRecommendation>(`/storyboard-crud/recommendations/${recommendationId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteShotRecommendation: (recommendationId: string) =>
    request<void>(`/storyboard-crud/recommendations/${recommendationId}`, { method: 'DELETE' }),

  createCharacter: (
    storyId: string,
    payload: { name: string; role?: string; physical_description?: string },
  ) =>
    request<Character>(`/storyboard/stories/${storyId}/characters`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateCharacter: (characterId: string, payload: Record<string, unknown>) =>
    optionalRequest<Character>(`/storyboard/characters/${characterId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteCharacter: (characterId: string, reason?: string) =>
    optionalRequest<void>(
      `/storyboard/characters/${characterId}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'DELETE' },
    ),
  listCharacters: (storyId: string) =>
    optionalRequest<Character[]>(`/storyboard/stories/${storyId}/characters`),

  createVoiceProfile: (storyId: string, payload: VoiceProfileCreatePayload) =>
    optionalRequest<Voice>(`/voices/stories/${storyId}/profiles`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateVoice: (voiceId: string, payload: VoiceProfileUpdatePayload) =>
    optionalRequest<Voice>(`/voices/profiles/${voiceId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteVoice: (voiceId: string, reason?: string) =>
    optionalRequest<void>(
      `/voices/profiles/${voiceId}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'DELETE' },
    ),
  listVoiceProfiles: (storyId: string) => optionalRequest<Voice[]>(`/voices/stories/${storyId}/profiles`),
  listVoiceRecipes: (voiceId: string) =>
    optionalRequest<VoiceRecipe[]>(`/voices/profiles/${voiceId}/recipes`),
  createVoiceRecipe: (voiceId: string, payload: VoiceRecipeCreatePayload) =>
    optionalRequest<VoiceRecipe>(`/voices/profiles/${voiceId}/recipes`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listVoicePreviews: (voiceId: string) =>
    optionalRequest<VoicePreview[]>(`/voices/profiles/${voiceId}/previews`),
  selectVoicePreview: (previewId: string, selected = true) =>
    optionalRequest<VoicePreview>(`/voices/previews/${previewId}/select`, {
      method: 'POST',
      body: JSON.stringify({ selected }),
    }),
  approveVoice: (voiceId: string, approvedBy: string, allowWithoutPreview = true) =>
    optionalRequest<VoiceApproveResult>(`/voices/profiles/${voiceId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        approved_by: approvedBy,
        allow_without_preview: allowWithoutPreview,
      }),
    }),
  /** Explicit provider-safe preview job. Never invoked automatically. */
  requestVoicePreview: (voiceId: string, previewText: string) =>
    optionalRequest<VoicePreviewJob>(`/voices/profiles/${voiceId}/previews`, {
      method: 'POST',
      body: JSON.stringify({ preview_text: previewText, owner: 'cineforge-storyboard-studio' }),
    }),
  getVoicePreviewJob: (jobId: string) => optionalRequest<VoicePreviewJob>(`/voices/preview-jobs/${jobId}`),

  listVoiceSourceAssets: (projectId: string) =>
    optionalRequest<PlanningMediaAssetList>(`/assets/projects/${projectId}?kind=voice_source`),
  uploadVoiceSourceAsset: (projectId: string, file: File, consentConfirmed: boolean) => {
    const query = new URLSearchParams({
      kind: 'voice_source',
      original_filename: file.name,
      source_type: 'user_upload',
      consent_confirmed: String(consentConfirmed),
    })
    return optionalRequest<PlanningMediaAssetUpload>(`/assets/projects/${projectId}/upload?${query}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
  },

  listStartingImageAssets: (projectId: string) =>
    optionalRequest<PlanningMediaAssetList>(`/assets/projects/${projectId}?kind=starting_image`),
  listVideoSourceAssets: (projectId: string) =>
    optionalRequest<PlanningMediaAssetList>(`/assets/projects/${projectId}?kind=video_source`),
  uploadVideoSourceAsset: (projectId: string, file: File) => {
    const query = new URLSearchParams({
      original_filename: file.name,
      source_type: 'user_upload',
    })
    return optionalRequest<PlanningMediaAssetUpload>(
      `/video/phase-7/projects/${projectId}/sources/upload?${query}`,
      {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      },
    )
  },
  listArtDirectionReferenceAssets: (projectId: string) =>
    optionalRequest<PlanningMediaAssetList>(
      `/assets/projects/${projectId}?kind=art_direction_reference`,
    ),
  uploadStartingImageAsset: (projectId: string, file: File) => {
    const query = new URLSearchParams({
      kind: 'starting_image',
      original_filename: file.name,
      source_type: 'user_upload',
    })
    return optionalRequest<PlanningMediaAssetUpload>(`/assets/projects/${projectId}/upload?${query}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
  },
  updateStartingImageApproval: (assetId: string, payload: StartingImageApprovalUpdate) =>
    request<PlanningMediaAsset>(`/assets/${assetId}/starting-image-approval`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  listCharacterReferenceAssets: (projectId: string) =>
    optionalRequest<PlanningMediaAssetList>(`/assets/projects/${projectId}?kind=character_reference`),
  uploadCharacterReferenceAsset: (projectId: string, file: File) => {
    const query = new URLSearchParams({
      kind: 'character_reference',
      original_filename: file.name,
      source_type: 'user_upload',
    })
    return optionalRequest<PlanningMediaAssetUpload>(`/assets/projects/${projectId}/upload?${query}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
  },
  listCharacterReferences: (characterId: string) =>
    optionalRequest<CharacterReferenceLink[]>(`/assets/characters/${characterId}/references`),
  linkCharacterReference: (
    characterId: string,
    payload: {
      asset_id: string
      reference_role: 'primary' | 'alternate' | 'expression' | 'costume' | 'detail'
      approved: boolean
      order_index: number
    },
  ) =>
    optionalRequest<CharacterReferenceLink>(`/assets/characters/${characterId}/references`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  unlinkCharacterReference: (linkId: string) =>
    optionalRequest<void>(`/assets/character-references/${linkId}`, { method: 'DELETE' }),

  runtimeCatalog: () => optionalRequest<RuntimeCatalog>('/runtime-catalog'),
  localModelInventory: () =>
    optionalRequest<LocalModelInventory>('/runtime-catalog/local-model-inventory'),
  listRuntimeWorkflowTemplates: () =>
    optionalRequest<RuntimeCatalogWorkflowTemplate[]>('/runtime-catalog/workflow-templates'),

  listProviderProfiles: () => request<ProviderProfile[]>('/storyboard-crud/provider-profiles'),
  listPlanningProviders: () => request<ProviderCatalogResponse>('/providers'),
  getPlanningProvider: (providerIdentifier: string) =>
    request<ProviderCatalogEntry>(`/providers/${encodeURIComponent(providerIdentifier)}`),
  getPlanningProviderCapabilities: (providerIdentifier: string) =>
    request<ProviderCapabilitiesResponse>(`/providers/${encodeURIComponent(providerIdentifier)}/capabilities`),
  testPlanningProviderConnection: (providerIdentifier: string, timeoutSec = 3) =>
    request<ProviderConnectionTestResponse>(`/providers/${encodeURIComponent(providerIdentifier)}/connection-test`, {
      method: 'POST',
      body: JSON.stringify({ timeout_sec: timeoutSec }),
    }),
  getProviderProfileCapabilities: (profileId: string) =>
    request<ProviderProfileCapabilitiesResponse>(`/storyboard-crud/provider-profiles/${profileId}/capabilities`),
  createProviderProfile: (payload: ProviderProfileCreatePayload) =>
    request<ProviderProfile>('/storyboard-crud/provider-profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProviderProfile: (profileId: string, payload: Partial<ProviderProfileCreatePayload>) =>
    request<ProviderProfile>(`/storyboard-crud/provider-profiles/${profileId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteProviderProfile: (profileId: string) =>
    request<void>(`/storyboard-crud/provider-profiles/${profileId}`, { method: 'DELETE' }),
  listTaskProviderAssignments: (storyId: string) =>
    request<TaskProviderAssignment[]>(`/storyboard-crud/stories/${storyId}/task-assignments`),
  createTaskProviderAssignment: (storyId: string, payload: TaskProviderAssignmentPayload) =>
    request<TaskProviderAssignment>(`/storyboard-crud/stories/${storyId}/task-assignments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateTaskProviderAssignment: (
    assignmentId: string,
    payload: Partial<Omit<TaskProviderAssignmentPayload, 'task_type'>>,
  ) =>
    request<TaskProviderAssignment>(`/storyboard-crud/task-assignments/${assignmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteTaskProviderAssignment: (assignmentId: string) =>
    request<void>(`/storyboard-crud/task-assignments/${assignmentId}`, { method: 'DELETE' }),
  validateStoryRouting: (storyId: string, payload: RoutingPreflightPayload) =>
    request<RoutingPreflightResponse>(`/stories/${storyId}/routing/validate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getSettings: (projectId: string) =>
    optionalRequest<ProjectStoryboardSettings>(`/projects/${projectId}/storyboard-settings`),
  updateSettings: (projectId: string, payload: ProjectStoryboardSettingsUpdate) =>
    optionalRequest<ProjectStoryboardSettings>(`/projects/${projectId}/storyboard-settings`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  approveStoryboard: (storyId: string, approvedBy: string, expectedRevision: string) =>
    request(`/storyboard/stories/${storyId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy, expected_revision: expectedRevision }),
    }),

  exportLinks: (storyId: string): ExportLinks => ({
    json_url: exportJsonUrl(storyId),
    shot_list_csv_url: exportShotListCsvUrl(storyId),
    pdf_available: false,
    edl_available: false,
    render_package_available: false,
  }),
}
