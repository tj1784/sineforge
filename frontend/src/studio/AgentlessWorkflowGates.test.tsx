import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  api,
  type ProjectStoryboardSettings,
  type AgentlessWorkflowProfile,
} from '../api/client'
import { AppShell } from '../components/AppShell'
import { StudioRouter } from './StudioRouter'
import { StudioContext, type StudioContextValue } from './StudioState'
import { demoAggregate, demoReadiness } from './demoPhaseA'

const profile: AgentlessWorkflowProfile = {
  project_id: 'agentless-project',
  workflow_lane: 'agentless',
  profile_ref: 'agentless-scene-reset@1',
  display_name: 'Agentless Workflow',
  agent_runtime_required: true,
  local_planning_agent_required: true,
  hosted_planning_agents_allowed: false,
  default_planning_agent: 'qwen',
  selected_planning_agent: 'qwen',
  prompt_artifact_format: 'json',
  prompt_artifact_extension: '.json',
  deterministic_python_orchestrator: true,
  logical_scene_duration_range_sec: [3, 20],
  default_segment_duration_sec: 10,
  default_fps: 24,
  default_ten_second_frame_count: 241,
  default_ten_second_playback_duration_sec: 241 / 24,
  ltx_frame_policy: '8n+1',
  max_logical_scenes: 50,
  allowed_resolutions: [[768, 448], [960, 544]],
  batch_size: 1,
  max_active_gpu_jobs: 1,
  max_attempts_per_generation_stage: 3,
  default_master_policy: {
    intermediate_codec: 'prores_422_hq',
    delivery_codec: 'h264',
    delivery_encode_count: 1,
    intermediate_reencoding_allowed: false,
    anchor_format: 'png',
  },
  pipeline: ['anchor', 'anchor_qa', 'video', 'video_qa', 'master'],
  non_cumulative_guarantees: [
    'Every segment creates a fresh lossless FLUX.2 PNG anchor.',
    'No segment consumes a previous clip or previous final frame.',
  ],
  workflow_requirements: [],
  readiness: {
    ready_to_execute: false,
    workflows_admitted: false,
    submission_supported: false,
    admissions: [
      {
        role: 'flux_anchor',
        status: 'missing_exact_pin',
        admitted: false,
        detail: 'Exact FLUX workflow pin required.',
      },
      {
        role: 'ltx_ingredients_i2v',
        status: 'missing_exact_pin',
        admitted: false,
        detail: 'Exact LTX workflow pin required.',
      },
    ],
    blockers: [
      {
        code: 'agentless_execution_boundary_not_implemented',
        message: 'Planning and dry-run only.',
      },
    ],
  },
}

const agentlessSettings: ProjectStoryboardSettings = {
  id: 'settings-1',
  project_id: demoAggregate.story.project_id,
  settings_version: 1,
  shot_duration_min_sec: 3,
  shot_duration_max_sec: 10,
  continuity_policy_json: {
    require_fresh_scene_anchor: true,
    allow_cross_scene_continuity: false,
    allow_previous_video_frame_handoff: false,
  },
  prompting_policy_json: {
    workflow_lane: 'agentless',
    orchestration_mode: 'deterministic_python',
    planning_agent: 'qwen',
    prompt_artifact_format: 'json',
  },
  voice_policy_json: {},
  approval_policy_json: {
    require_exact_duration: true,
  },
  speaking_rate: 1,
  aspect_ratio: '16:9',
  preview_width: 1280,
  preview_height: 720,
  final_width: 1920,
  final_height: 1080,
  fps: 24,
  captions_enabled: true,
  audio_enabled: true,
  production_profile_key: 'ltx_base@2',
  production_profile_snapshot_json: {},
  stitch_stage: 'phase7_before_audio',
  prefer_hosted_providers: false,
  prefer_local_providers: true,
  allow_model_download: false,
  allow_rendering: false,
  require_voice_consent: true,
  require_production_plan_approval: true,
}

function studioValue(): StudioContextValue {
  const resolved = async () => undefined
  return {
    backendStatus: 'ok',
    navigate: vi.fn(),
    workflowLane: 'agentless',
    projectId: 'agentless-project',
    setProjectId: vi.fn(),
    storyId: demoAggregate.story.id,
    setStoryId: vi.fn(),
    data: demoAggregate,
    readiness: demoReadiness,
    message: '',
    setMessage: vi.fn(),
    loadState: 'ready',
    error: null,
    selectedShot: null,
    setSelectedShot: vi.fn(),
    animaticOpen: false,
    setAnimaticOpen: vi.fn(),
    busy: false,
    reload: resolved,
    createStory: resolved,
    loadExistingStory: resolved,
    addHierarchy: resolved,
    addCharacter: resolved,
    addVoice: async () => true,
    saveShot: resolved,
    saveNarration: resolved,
    savePromptPackage: resolved,
    approvePlan: resolved,
    updateStoryFields: resolved,
  }
}

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
  vi.spyOn(api, 'getAgentlessWorkflowProfile').mockResolvedValue(profile)
  vi.spyOn(api, 'getSettings').mockResolvedValue(agentlessSettings)
  vi.spyOn(api, 'listOrchestrationRuns').mockResolvedValue([])
  vi.spyOn(api, 'listStoryProposals').mockResolvedValue([])
  vi.spyOn(api, 'listProviderProfiles').mockResolvedValue([])
  vi.spyOn(api, 'listPlanningProviders').mockResolvedValue({
    schema_name: 'planning.provider_catalog.v1',
    generated_at: '2026-07-30T00:00:00Z',
    providers: [],
  })
  vi.spyOn(api, 'listLmStudioModels').mockResolvedValue({
    schema_name: 'runtime.lm_studio_models.v1',
    status: 'ok',
    reachable: true,
    active_model_id: 'qwen3-4b',
    configured_model_id: 'qwen3-4b',
    error: null,
    models: [
      {
        model_id: 'qwen3-4b',
        key: 'qwen3-4b',
        display_name: 'Qwen3 4B Hivemind',
        filename: 'qwen3-4b-q4_k_m.gguf',
        publisher: 'local',
        architecture: 'qwen',
        quantization: 'Q4_K_M',
        params_string: '4B',
        size_bytes: null,
        max_context_length: 8192,
        context_length: 8192,
        parallel: 1,
        installed: true,
        loaded: true,
        selected: true,
        loaded_instance_ids: ['qwen3-4b'],
      },
    ],
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Agentless Studio boundaries', () => {
  it('does not expose Studio mutations before the persisted lane is loaded', () => {
    render(
      <StudioContext.Provider
        value={{
          ...studioValue(),
          workflowLane: null,
          data: null,
          loadState: 'empty',
        }}
      >
        <StudioRouter page="overview" />
      </StudioContext.Provider>,
    )

    expect(screen.getByText('Loading the project workflow boundary…')).toBeTruthy()
    expect(screen.queryByText('Create planning story')).toBeNull()
  })

  it('replaces unsafe deep-linked Studio pages with the Agentless boundary', async () => {
    render(
      <StudioContext.Provider value={studioValue()}>
        <StudioRouter page="routing" />
      </StudioContext.Provider>,
    )

    expect(
      screen.getByText(/Provider model routing is unavailable in Agentless Workflow/),
    ).toBeTruthy()
    expect(await screen.findByText('Agentless scene-reset workflow')).toBeTruthy()
    expect(screen.getByText('Submission disabled')).toBeTruthy()
  })

  it('blocks the unrestricted native API Runner when deep-linked', async () => {
    render(
      <StudioContext.Provider value={studioValue()}>
        <StudioRouter page="api-runner" />
      </StudioContext.Provider>,
    )

    expect(
      screen.getByText(/unrestricted native API Runner is unavailable in Agentless Workflow/i),
    ).toBeTruthy()
    expect(await screen.findByText('Agentless scene-reset workflow')).toBeTruthy()
    expect(screen.getByText('Submission disabled')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'SineForge API Runner' })).toBeNull()
  })

  it('keeps local planning controls while removing generic execution navigation', () => {
    render(
      <AppShell
        activePage="overview"
        backendStatus="ok"
        projectId="agentless-project"
        projectName="Agentless Podcast"
        workflowLane="agentless"
        projectCount={1}
        view="studio"
        onNavigate={vi.fn()}
        onOpenProjects={vi.fn()}
        onCreateProject={vi.fn()}
      >
        <p>Safe project content</p>
      </AppShell>,
    )

    expect(screen.queryByText('Starting images')).toBeNull()
    expect(screen.getByText(/Story & chapters/i)).toBeTruthy()
    expect(screen.queryByText('Model routing')).toBeNull()
    expect(screen.queryByText('API Caller')).toBeNull()
    expect(screen.queryByText('API Runner')).toBeNull()
    expect(screen.getByText('Agentless scene reset')).toBeTruthy()
    expect(screen.getByLabelText('Active LM Studio planning model')).toBeTruthy()
    expect(screen.getByText('AGENTLESS')).toBeTruthy()
  })

  it('locks Story planning to the selected local agent without hosted or mock choices', async () => {
    render(
      <StudioContext.Provider value={studioValue()}>
        <StudioRouter page="story" />
      </StudioContext.Provider>,
    )

    expect(
      await screen.findByText(
        /locked to the selected local Qwen3 4B Hivemind agent/i,
      ),
    ).toBeTruthy()
    expect(
      (screen.getByLabelText('Routing mode') as HTMLSelectElement).disabled,
    ).toBe(true)
    expect(
      (screen.getByLabelText('Provider preference') as HTMLSelectElement)
        .disabled,
    ).toBe(true)
    expect(screen.queryByText('Prefer hosted only')).toBeNull()
    expect(screen.queryByText('Prefer local and allow hosted')).toBeNull()
    expect(screen.queryByText(/Built-in mock/)).toBeNull()
  })

  it('shows immutable Agentless production settings as locked', async () => {
    render(
      <StudioContext.Provider value={studioValue()}>
        <StudioRouter page="settings" />
      </StudioContext.Provider>,
    )

    expect(await screen.findByText(/Agentless policy locks LTX Base v2/)).toBeTruthy()
    expect(
      (screen.getByLabelText(/Video production profile/) as HTMLSelectElement)
        .disabled,
    ).toBe(true)
    expect(
      (screen.getByLabelText('Frames per second') as HTMLInputElement).disabled,
    ).toBe(true)
    expect(
      (
        screen.getByLabelText(
          /Allow model and LoRA downloads/,
        ) as HTMLInputElement
      ).disabled,
    ).toBe(true)
    expect(
      (
        screen.getByLabelText(
          /Allow rendering \/ video generation jobs/,
        ) as HTMLInputElement
      ).disabled,
    ).toBe(true)
  })
})
