import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { Projects } from './Projects'

vi.mock('../api/client', () => ({
  api: {
    createProjectWorkspace: vi.fn(),
    createProjectFromSulphur: vi.fn(),
    restartComfyUi: vi.fn(),
    comfyRestartStatus: vi.fn(),
    listProjects: vi.fn(),
    listStories: vi.fn(),
  },
}))

const workspace = {
  project: {
    id: 'project-1',
    name: 'The Test Film',
    description: 'A test',
    created_at: '2026-07-17T00:00:00Z',
    persistence: 'db',
  },
  story: { id: 'story-1' },
  settings: { id: 'settings-1' },
  idempotent_replay: false,
}

function reachFinalStep() {
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

describe('new project workspace', () => {
  it('submits the wizard once and preserves its story and production values', async () => {
    vi.mocked(api.createProjectWorkspace).mockResolvedValue(workspace as never)
    const onOpenProject = vi.fn()
    render(<Projects mode="create" onOpenProject={onOpenProject} />)
    reachFinalStep()

    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'Families' } })
    fireEvent.change(screen.getByLabelText('Aspect ratio'), { target: { value: '2.39:1' } })
    fireEvent.change(screen.getByLabelText('Frame rate'), { target: { value: '30' } })
    fireEvent.change(screen.getByLabelText('Privacy preference'), {
      target: { value: 'Hosted providers allowed' },
    })
    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete script' }))

    await waitFor(() => expect(api.createProjectWorkspace).toHaveBeenCalledTimes(1))
    expect(api.createProjectWorkspace).toHaveBeenCalledWith(expect.objectContaining({
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
      speaking_rate: 1,
      prefer_hosted_providers: true,
      prefer_local_providers: true,
      allow_model_download: true,
      allow_rendering: true,
      require_production_plan_approval: true,
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
    }))
    expect(onOpenProject).toHaveBeenCalledWith('project-1', 'The Test Film')
  })

  it('shows a useful failure and reuses the idempotency key on retry', async () => {
    vi.mocked(api.createProjectWorkspace)
      .mockRejectedValueOnce(new Error('Workspace creation failed safely; no partial project was kept.'))
      .mockResolvedValueOnce(workspace as never)
    render(<Projects mode="create" />)
    reachFinalStep()

    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete script' }))
    expect((await screen.findByRole('alert')).textContent).toContain(
      'Workspace creation failed safely; no partial project was kept.',
    )
    fireEvent.click(screen.getByRole('button', { name: '✦ Create project & complete script' }))

    await waitFor(() => expect(api.createProjectWorkspace).toHaveBeenCalledTimes(2))
    const firstKey = vi.mocked(api.createProjectWorkspace).mock.calls[0][0].idempotency_key
    const secondKey = vi.mocked(api.createProjectWorkspace).mock.calls[1][0].idempotency_key
    expect(secondKey).toBe(firstKey)
  })
})

describe('project workspace navigation', () => {
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
      screen.getByLabelText('Describe the complete CineForge project for Sulphur'),
      { target: { value: sourcePrompt } },
    )
    fireEvent.click(screen.getByRole('button', { name: /Create complete project/ }))

    await waitFor(() => expect(api.createProjectFromSulphur).toHaveBeenCalledTimes(1))
    expect(api.createProjectFromSulphur).toHaveBeenCalledWith({
      idempotency_key: expect.stringMatching(/^sulphur-project-/),
      prompt: sourcePrompt,
    })
    expect(onOpenProject).toHaveBeenCalledWith('project-1', 'The Test Film')
  })

  it('shows the API Runner and completes a visible ComfyUI restart', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])
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

    render(<Projects mode="list" onNavigateStudio={vi.fn()} />)

    expect(screen.getByRole('link', { name: /Open API Runner/ }).getAttribute('href'))
      .toBe('http://127.0.0.1:8022')
    fireEvent.click(screen.getByRole('button', { name: /Restart ComfyUI/ }))

    expect(await screen.findByText('ComfyUI restarted successfully with CUDA device 0.'))
      .toBeTruthy()
    expect(api.restartComfyUi).toHaveBeenCalledTimes(1)
    expect(api.comfyRestartStatus).toHaveBeenCalledWith('a'.repeat(32))
  })
})
