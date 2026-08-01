import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { AppShell } from './AppShell'

vi.mock('../api/client', () => ({
  api: {
    listLmStudioModels: vi.fn(),
    activateLmStudioModel: vi.fn(),
    engineStatus: vi.fn(),
  },
}))

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches: false,
      media: '(max-width: 900px)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
  vi.mocked(api.listLmStudioModels).mockResolvedValue({
    reachable: false,
    base_url: 'http://127.0.0.1:1234',
    default_model_id: 'qwen',
    active_model_id: null,
    models: [],
    error: null,
  } as never)
  vi.mocked(api.engineStatus).mockResolvedValue({
    schema: 'sineforge.comfy-engine/v1',
    distribution: 'BlokeyUI',
    engine: 'ComfyUI',
    mode: 'bundled',
    managed: true,
    autostart: true,
    status: 'running',
    ready: true,
    reachable: true,
    checks: { system_stats: true, sineforge_bridge: true, required_nodes: true },
    missing_required_nodes: [],
    pid: 8190,
    started_at_epoch: 1,
    stopped_at_epoch: null,
    last_exit_code: null,
    last_error: null,
    api_base_url: 'http://127.0.0.1:8190',
    input_root: 'storage/inputs',
    output_root: 'storage/outputs',
    log_root: 'storage/runtime/comfyui/logs',
    source_root: 'BlokeyUI/ComfyUI',
    python_runtime: 'engine/python_embeded/python.exe',
    custom_nodes_root: 'engine/custom_nodes',
    launch_preset: 'blokeyui-source-ltx-compatibility-runtime',
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderShell(onNavigate = vi.fn()) {
  render(
    <AppShell
      activePage="overview"
      backendStatus="ok"
      projectId="project-native-runner"
      projectName="Native Runner Project"
      workflowLane="cineforge_studio"
      projectCount={1}
      view="studio"
      onNavigate={onNavigate}
      onOpenProjects={vi.fn()}
      onCreateProject={vi.fn()}
    >
      <p>Project workspace</p>
    </AppShell>,
  )
  return onNavigate
}

describe('AppShell API Runner integration', () => {
  it('navigates to the distinct native API Runner page', () => {
    const onNavigate = renderShell()
    const projectNavigation = screen.getByLabelText('Current project navigation')
    expect(within(projectNavigation).queryByRole('button', { name: 'API Caller' })).toBeNull()
    fireEvent.click(within(projectNavigation).getByRole('button', { name: 'API Runner' }))

    expect(onNavigate).toHaveBeenCalledWith('api-runner')
  })

  it('opens the Sineforge-native Engine workspace without external UI links', async () => {
    const onNavigate = renderShell()
    fireEvent.click(screen.getByRole('button', { name: /Sineforge engine/ }))

    const button = await screen.findByRole('button', { name: /Open Engine workspace/ })
    fireEvent.click(button)

    expect(onNavigate).toHaveBeenCalledWith('api-runner')
    expect(screen.queryByRole('link', { name: /ComfyUI|ComfyAPI Runner/ })).toBeNull()
  })
})
