import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { AppShell } from './AppShell'

vi.mock('../api/client', () => ({
  api: {
    listLmStudioModels: vi.fn(),
    activateLmStudioModel: vi.fn(),
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
    fireEvent.click(within(projectNavigation).getByRole('button', { name: 'API Runner' }))

    expect(onNavigate).toHaveBeenCalledWith('api-runner')
  })

  it('preserves the separate standalone ComfyAPI Runner link', async () => {
    renderShell()
    fireEvent.click(screen.getByRole('button', { name: /Local AI tools/ }))

    const link = await screen.findByRole('link', { name: /Open ComfyAPI Runner/ })
    expect(link.getAttribute('href')).toBe('http://127.0.0.1:8022')
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noreferrer')
  })
})
