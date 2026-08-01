import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BackendUnavailableError, api } from '../api/client'
import { Projects } from './Projects'

vi.mock('../api/client', () => ({
  BackendUnavailableError: class BackendUnavailableError extends Error {},
  api: {
    createProjectWorkspace: vi.fn(),
    createProjectFromSulphur: vi.fn(),
    restartComfyUi: vi.fn(),
    comfyRestartStatus: vi.fn(),
    engineStatus: vi.fn(),
    listLmStudioModels: vi.fn(),
    activateLmStudioModel: vi.fn(),
    freeNativeApiRunnerMemory: vi.fn(),
    listProjects: vi.fn(),
    listStories: vi.fn(),
  },
}))

const lmStudioCatalog = {
  schema_name: 'runtime.lm_studio_models.v1',
  status: 'ok',
  reachable: true,
  active_model_id: 'qwen3-4b-hivemind',
  configured_model_id: 'qwen3-4b-hivemind',
  error: null,
  models: [
    {
      model_id: 'qwen3-4b-hivemind',
      key: 'qwen3-4b-hivemind',
      display_name: 'Qwen3 4B Hivemind',
      filename: 'qwen.gguf',
      publisher: null,
      architecture: null,
      quantization: 'Q4_K_M',
      params_string: '4B',
      size_bytes: null,
      max_context_length: 32_768,
      context_length: 8_192,
      parallel: 1,
      installed: true,
      loaded: true,
      selected: true,
      loaded_instance_ids: ['qwen3-4b-hivemind'],
    },
    {
      model_id: 'sulphur-2-base',
      key: 'sulphur-2-base',
      display_name: 'Sulphur 2 Base',
      filename: 'sulphur.gguf',
      publisher: null,
      architecture: null,
      quantization: 'Q8_0',
      params_string: '22B',
      size_bytes: null,
      max_context_length: 32_768,
      context_length: null,
      parallel: null,
      installed: true,
      loaded: false,
      selected: false,
      loaded_instance_ids: [],
    },
    {
      model_id: 'qwen3.5-9b-defiant',
      key: 'qwen3.5-9b-defiant',
      display_name: 'Qwen3.5 9B The Defiant',
      filename: 'qwen3.5-9b.gguf',
      publisher: null,
      architecture: null,
      quantization: 'Q5_K_M',
      params_string: '9B',
      size_bytes: null,
      max_context_length: 65_536,
      context_length: null,
      parallel: null,
      installed: true,
      loaded: false,
      selected: false,
      loaded_instance_ids: [],
    },
  ],
} as const

const workspace = {
  project: {
    id: 'project-1',
    name: 'The Test Film',
    description: 'A test',
    workflow_lane: 'cineforge_studio',
    created_at: '2026-07-17T00:00:00Z',
    persistence: 'db',
  },
  story: { id: 'story-1' },
  settings: { id: 'settings-1' },
  idempotent_replay: false,
}

function reachFinalStep(
  workflowLane: 'cineforge_studio' | 'agentless' = 'cineforge_studio',
) {
  fireEvent.click(
    screen.getByRole('radio', {
      name:
        workflowLane === 'agentless'
          ? /Agentless Workflow/
          : /CineForge Studio Workflow/,
    }),
  )
  fireEvent.change(screen.getByPlaceholderText('Leave blank and CineForge will create the title'), {
    target: { value: 'The Test Film' },
  })
  fireEvent.change(screen.getByPlaceholderText('What are you creating, and what should the audience experience?'), {
    target: { value: 'A test' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Continue →' }))
  fireEvent.change(screen.getByPlaceholderText('Describe the complete story, required moments, and creative boundaries in one prompt…'), {
    target: { value: 'The complete source.' },
  })
  fireEvent.change(screen.getByLabelText('Number of chapters'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('CH01 title'), { target: { value: 'Opening Act' } })
  fireEvent.change(screen.getByLabelText('CH01 source prompt'), {
    target: { value: 'Start with the inciting discovery.' },
  })
  fireEvent.change(screen.getByLabelText('CH02 title'), { target: { value: 'Final Choice' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue →' }))
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  vi.mocked(api.listLmStudioModels).mockResolvedValue(lmStudioCatalog as never)
  vi.mocked(api.engineStatus).mockResolvedValue({
    status: 'running',
    ready: true,
    last_error: null,
  } as never)
  vi.mocked(api.activateLmStudioModel).mockImplementation(async (modelId) => {
    const model = lmStudioCatalog.models.find((item) => item.model_id === modelId)
    if (!model) throw new Error('Model not found')
    return {
      status: 'loaded',
      active_model_id: model.model_id,
      loaded: true,
      load_time_seconds: 0.1,
      model: {
        ...model,
        loaded: true,
        selected: true,
        loaded_instance_ids: [model.model_id],
      },
    } as never
  })
})

describe('new project workspace', () => {
  it('requires an explicit workflow lane before leaving Step 1', () => {
    render(<Projects mode="create" />)

    const studioLane = screen.getByRole('radio', {
      name: /CineForge Studio Workflow/,
    }) as HTMLInputElement
    const agentlessLane = screen.getByRole('radio', {
      name: /Agentless Workflow/,
    }) as HTMLInputElement
    expect(studioLane.checked).toBe(false)
    expect(agentlessLane.checked).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Continue →' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'Choose CineForge Studio Workflow or Agentless Workflow.',
    )
    expect(screen.getByText('Choose the workflow and project foundation')).toBeTruthy()
  })

  it('submits the wizard once and preserves its story and production values', async () => {
    vi.mocked(api.createProjectWorkspace).mockResolvedValue(workspace as never)
    const onOpenProject = vi.fn()
    render(<Projects mode="create" onOpenProject={onOpenProject} />)
    reachFinalStep()

    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'Families' } })
    fireEvent.change(screen.getByLabelText('Aspect ratio'), { target: { value: '2.39:1' } })
    fireEvent.change(screen.getByLabelText('Frame rate'), { target: { value: '30' } })
    fireEvent.change(screen.getByLabelText(/Base-model profile/), { target: { value: 'ltx_base@2' } })
    fireEvent.change(screen.getByLabelText('Picture stitch stage'), { target: { value: 'phase8_before_foley' } })
    fireEvent.change(screen.getByLabelText('Privacy preference'), {
      target: { value: 'Hosted providers allowed' },
    })
    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete Phases 1–5' }))

    await waitFor(() => expect(api.createProjectWorkspace).toHaveBeenCalledTimes(1))
    expect(api.createProjectWorkspace).toHaveBeenCalledWith(expect.objectContaining({
      workflow_lane: 'cineforge_studio',
      name: 'The Test Film',
      description: 'A test',
      base_story: 'The complete source.',
      audience: 'Families',
      aspect_ratio: '2.39:1',
      preview_width: 1280,
      preview_height: 536,
      final_width: 1920,
      final_height: 804,
      fps: 30,
      captions_enabled: true,
      audio_enabled: true,
      production_profile_key: 'ltx_base@2',
      stitch_stage: 'phase8_before_foley',
      speaking_rate: 1,
      prefer_hosted_providers: true,
      prefer_local_providers: true,
      allow_model_download: true,
      allow_rendering: true,
      require_production_plan_approval: false,
      requested_chapter_count: 2,
      chapter_intake: [
        expect.objectContaining({
          order_index: 0,
          title: 'Opening Act',
          source_prompt: 'Start with the inciting discovery.',
          target_duration_sec: 150,
        }),
        expect.objectContaining({
          order_index: 1,
          title: 'Final Choice',
          target_duration_sec: 150,
        }),
      ],
      run_phase_one: true,
      bootstrap_phase_plan: true,
      auto_approve_phases_through: 1,
      run_phases_two_through_five: true,
    }))
    expect(onOpenProject).toHaveBeenCalledWith('project-1', 'The Test Film')
  })

  it('uses Qwen locally for Agentless Phase 1 and keeps production deterministic', async () => {
    vi.mocked(api.createProjectWorkspace).mockResolvedValue({
      ...workspace,
      project: { ...workspace.project, workflow_lane: 'agentless' },
    } as never)
    render(<Projects mode="create" initialWorkflowLane="agentless" />)

    expect(
      (screen.getByRole('radio', { name: /Agentless Workflow/ }) as HTMLInputElement).checked,
    ).toBe(true)
    expect(
      (screen.getByRole('radio', { name: /Qwen3 4B Hivemind/ }) as HTMLInputElement).checked,
    ).toBe(true)

    fireEvent.change(screen.getByPlaceholderText('Leave blank and CineForge will create the title'), {
      target: { value: 'Deterministic Test' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Continue →' }))
    fireEvent.change(screen.getByPlaceholderText('Describe the complete story, required moments, and creative boundaries in one prompt…'), {
      target: { value: 'Use the local agent and keep all prompt artifacts as JSON.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Continue →' }))

    expect((screen.getByLabelText('Frame rate') as HTMLSelectElement).value).toBe('24')
    expect((screen.getByLabelText(/Base-model profile/) as HTMLSelectElement).value).toBe(
      'ltx_base@2',
    )
    expect((screen.getByLabelText('Orchestration') as HTMLSelectElement).value).toBe('Manual')
    fireEvent.click(screen.getByRole('button', { name: 'Create with Qwen3 4B Hivemind' }))

    await waitFor(() => expect(api.createProjectWorkspace).toHaveBeenCalledTimes(1))
    expect(api.createProjectWorkspace).toHaveBeenCalledWith(expect.objectContaining({
      workflow_lane: 'agentless',
      planning_agent: 'qwen',
      prompt_artifact_format: 'json',
      prompt_schema_version: 'sineforge.local-planning-prompt/v1',
      fps: 24,
      production_profile_key: 'ltx_base@2',
      orchestration_mode: 'deterministic_python',
      allow_model_download: false,
      allow_rendering: false,
      prefer_hosted_providers: false,
      prefer_local_providers: true,
      run_phase_one: true,
      bootstrap_phase_plan: true,
      auto_approve_phases_through: 1,
      run_phases_two_through_five: true,
      require_production_plan_approval: false,
    }))
  })

  it('shows a useful failure and reuses the idempotency key on retry', async () => {
    vi.mocked(api.createProjectWorkspace)
      .mockRejectedValueOnce(new Error('Workspace creation failed safely; no partial project was kept.'))
      .mockResolvedValueOnce(workspace as never)
    render(<Projects mode="create" />)
    reachFinalStep()

    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete Phases 1–5' }))
    expect((await screen.findByRole('alert')).textContent).toContain(
      'Workspace creation failed safely; no partial project was kept.',
    )
    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete Phases 1–5' }))

    await waitFor(() => expect(api.createProjectWorkspace).toHaveBeenCalledTimes(2))
    const firstKey = vi.mocked(api.createProjectWorkspace).mock.calls[0][0].idempotency_key
    const secondKey = vi.mocked(api.createProjectWorkspace).mock.calls[1][0].idempotency_key
    expect(secondKey).toBe(firstKey)
  })
})

describe('project workspace navigation', () => {
  it('preserves project data semantics and recovers after a backend outage', async () => {
    vi.mocked(api.listProjects)
      .mockRejectedValueOnce(new BackendUnavailableError('temporarily unavailable'))
      .mockResolvedValueOnce([workspace.project] as never)
    vi.mocked(api.listStories).mockResolvedValue([])

    render(<Projects mode="list" />)

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByText('No projects yet.')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry now' }))

    expect(await screen.findByText('The Test Film')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(api.listProjects).toHaveBeenCalledTimes(2)
  })

  it('shows the persisted workflow lane on project cards', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([workspace.project] as never)
    vi.mocked(api.listStories).mockResolvedValue([])

    render(<Projects mode="list" />)

    expect(await screen.findByText('CineForge Studio Workflow')).toBeTruthy()
  })

  it('opens a Gold home shortcut directly in the selected project', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([workspace.project] as never)
    vi.mocked(api.listStories).mockResolvedValue([])
    const onOpenProjectPage = vi.fn()
    const onNavigateStudio = vi.fn()

    render(
      <Projects
        currentProjectId="project-1"
        onOpenProjectPage={onOpenProjectPage}
        onNavigateStudio={onNavigateStudio}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: /Storyboard/ }))

    expect(onOpenProjectPage).toHaveBeenCalledWith('project-1', 'The Test Film', 'storyboard')
    expect(onNavigateStudio).not.toHaveBeenCalled()
  })

  it('creates a complete project from the homepage through Sulphur', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])
    vi.mocked(api.createProjectFromSulphur).mockResolvedValue({
      ...workspace,
      intake_provider: 'sulphur',
      intake_model: 'sulphur-2-base',
      source_prompt_preserved: true,
      target_duration_sec: 125,
      planned_scene_count: 16,
      nominal_scene_duration_sec: 8,
      clip_duration_range_sec: [6, 10],
    } as never)
    const onOpenProject = vi.fn()
    const sourcePrompt =
      'Create a 2 minute 5 second noir film about a courier returning a lost letter.'

    render(
      <Projects
        mode="list"
        onOpenProject={onOpenProject}
        onNavigateStudio={vi.fn()}
      />,
    )

    fireEvent.change(
      screen.getByLabelText('Describe the complete CineForge project'),
      { target: { value: sourcePrompt } },
    )
    fireEvent.click(screen.getByRole('radio', { name: /CineForge Studio Workflow/ }))
    await screen.findByText(/3 LM Studio models available/)
    expect(screen.getByRole('radio', { name: /Qwen3.5 9B The Defiant/ })).toBeTruthy()
    const sulphurAgent = screen
      .getAllByRole('radio', { name: /Sulphur 2 Base/ })
      .find((element) => (element as HTMLInputElement).value === 'sulphur')
    expect(sulphurAgent).toBeTruthy()
    fireEvent.click(sulphurAgent as HTMLInputElement)
    const sulphurModel = screen
      .getAllByRole('radio', { name: /Sulphur 2 Base/ })
      .find((element) => (element as HTMLInputElement).value === 'sulphur-2-base')
    expect(sulphurModel).toBeTruthy()
    fireEvent.click(sulphurModel as HTMLInputElement)
    fireEvent.click(await screen.findByRole('button', { name: /Create with Sulphur/ }))

    await waitFor(() => expect(api.createProjectFromSulphur).toHaveBeenCalledTimes(1))
    expect(api.createProjectFromSulphur).toHaveBeenCalledWith({
      idempotency_key: expect.stringMatching(/^sulphur-project-/),
      prompt: sourcePrompt,
      workflow_lane: 'cineforge_studio',
      planning_agent: 'sulphur',
      planning_model_id: 'sulphur-2-base',
      prompt_artifact_format: 'json',
      prompt_schema_version: 'sineforge.local-planning-prompt/v1',
    })
    expect(onOpenProject).toHaveBeenCalledWith('project-1', 'The Test Film')
  })

  it('defaults Studio planning to Qwen and submits the JSON prompt contract', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])
    vi.mocked(api.createProjectFromSulphur).mockResolvedValue({
      ...workspace,
      intake_provider: 'qwen',
      intake_model: 'qwen3-4b-test',
      source_prompt_preserved: true,
      target_duration_sec: 60,
      planned_scene_count: 8,
      nominal_scene_duration_sec: 8,
      clip_duration_range_sec: [6, 10],
    } as never)
    const sourcePrompt = 'Create a complete 60-second story about a night train.'

    render(<Projects mode="list" onNavigateStudio={vi.fn()} />)

    fireEvent.click(screen.getByRole('radio', { name: /CineForge Studio Workflow/ }))
    await screen.findByText(/3 LM Studio models available/)
    const qwenAgent = screen
      .getAllByRole('radio', { name: /Qwen3 4B Hivemind/ })
      .find((element) => (element as HTMLInputElement).value === 'qwen')
    expect(qwenAgent).toBeTruthy()
    expect((qwenAgent as HTMLInputElement).checked).toBe(true)
    fireEvent.change(
      screen.getByLabelText('Describe the complete CineForge project'),
      { target: { value: sourcePrompt } },
    )
    fireEvent.click(screen.getByRole('button', { name: /Create with Qwen3 4B Hivemind/ }))

    await waitFor(() => expect(api.createProjectFromSulphur).toHaveBeenCalledTimes(1))
    expect(api.createProjectFromSulphur).toHaveBeenCalledWith({
      idempotency_key: expect.stringMatching(/^sulphur-project-/),
      prompt: sourcePrompt,
      workflow_lane: 'cineforge_studio',
      planning_agent: 'qwen',
      planning_model_id: 'qwen3-4b-hivemind',
      prompt_artifact_format: 'json',
      prompt_schema_version: 'sineforge.local-planning-prompt/v1',
    })
  })

  it('carries default Qwen into Agentless setup without invoking planning early', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])
    const onContinueAgentless = vi.fn()

    render(
      <Projects
        mode="list"
        onContinueAgentless={onContinueAgentless}
        onNavigateStudio={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('radio', { name: /Agentless Workflow/ }))
    expect(
      (screen.getByRole('radio', { name: /Qwen3 4B Hivemind/ }) as HTMLInputElement).checked,
    ).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Continue with Qwen3 4B Hivemind' }))

    expect(onContinueAgentless).toHaveBeenCalledWith('qwen')
    expect(api.createProjectFromSulphur).not.toHaveBeenCalled()
  })

  it('opens the in-app Engine and completes a visible bundled-engine restart', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])
    const onNavigateStudio = vi.fn()
    vi.mocked(api.restartComfyUi).mockResolvedValue({
      restart_id: 'a'.repeat(32),
      status: 'scheduled',
      message: 'Restart scheduled',
    })
    vi.mocked(api.comfyRestartStatus).mockResolvedValue({
      restart_id: 'a'.repeat(32),
      status: 'complete',
      message: 'ComfyUI restarted',
      complete: true,
      failed: false,
    })

    render(<Projects mode="list" onNavigateStudio={onNavigateStudio} />)

    fireEvent.click(screen.getByRole('button', { name: /Open Engine/ }))
    expect(onNavigateStudio).toHaveBeenCalledWith('api-runner')
    expect(screen.queryByRole('link', { name: /ComfyUI|API Runner/ })).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: /Restart engine/ }))

    expect(await screen.findByText('The bundled ComfyUI engine restarted successfully.'))
      .toBeTruthy()
    expect(api.restartComfyUi).toHaveBeenCalledTimes(1)
    expect(api.comfyRestartStatus).toHaveBeenCalledWith('a'.repeat(32))
  })
})
