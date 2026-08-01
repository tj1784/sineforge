import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, BackendUnavailableError, api } from './api/client'
import App from './App'
import {
  APP_NAVIGATION_REQUEST_EVENT,
  type AppNavigationRequestDetail,
} from './navigationGuard'

vi.mock('./api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number

    constructor(status: number) {
      super(`status ${status}`)
      this.status = status
    }
  },
  BackendUnavailableError: class BackendUnavailableError extends Error {},
  api: {
    listProjects: vi.fn(),
    getProject: vi.fn(),
    health: vi.fn(),
  },
}))

vi.mock('./components/AppShell', () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('./pages/Projects', () => ({
  Projects: ({ onNavigateStudio }: { onNavigateStudio?: (page: string) => void }) => (
    <div>
      Projects page
      <button type="button" onClick={() => onNavigateStudio?.('api-runner')}>
        Open Engine test
      </button>
    </div>
  ),
}))

vi.mock('./pages/StoryboardStudio', () => ({
  StoryboardStudio: ({ page }: { page: string }) => <div>Studio page: {page}</div>,
}))

vi.mock('./studio/pages/ApiRunnerPage', () => ({
  ApiRunnerPage: () => <div>Global Engine workspace</div>,
}))

const project = {
  id: 'project-native-runner',
  name: 'Native Runner Project',
  workflow_lane: 'cineforge_studio',
}

beforeEach(() => {
  window.history.replaceState(
    {},
    '',
    '/projects/project-native-runner/studio/api-runner',
  )
  Object.defineProperty(window, 'scrollTo', {
    configurable: true,
    value: vi.fn(),
  })
  vi.mocked(api.listProjects).mockResolvedValue([project] as never)
  vi.mocked(api.getProject).mockResolvedValue(project as never)
  vi.mocked(api.health).mockResolvedValue({ status: 'ok' } as never)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('App browser-history navigation', () => {
  it('routes popstate through the cancelable unsaved-navigation guard', async () => {
    render(<App />)
    expect(await screen.findByText('Studio page: api-runner')).toBeTruthy()

    let pendingNavigation: (() => void) | null = null
    const guard = (event: Event) => {
      const navigationEvent = event as CustomEvent<AppNavigationRequestDetail>
      navigationEvent.preventDefault()
      pendingNavigation = navigationEvent.detail.proceed
    }
    window.addEventListener(APP_NAVIGATION_REQUEST_EVENT, guard)

    try {
      act(() => {
        window.history.pushState({}, '', '/projects')
        window.dispatchEvent(new PopStateEvent('popstate'))
      })

      await waitFor(() => expect(pendingNavigation).toBeTypeOf('function'))
      expect(window.location.pathname).toBe(
        '/projects/project-native-runner/studio/api-runner',
      )
      expect(screen.getByText('Studio page: api-runner')).toBeTruthy()
      expect(screen.queryByText('Projects page')).toBeNull()

      const continueNavigation = pendingNavigation as unknown as (() => void)
      act(() => {
        continueNavigation()
      })
      await waitFor(() => expect(screen.getByText('Projects page')).toBeTruthy())
      expect(window.location.pathname).toBe('/projects')
    } finally {
      window.removeEventListener(APP_NAVIGATION_REQUEST_EVENT, guard)
    }
  })

  it('canonicalizes the legacy api-caller deep link to the native API Runner', async () => {
    window.history.replaceState(
      {},
      '',
      '/projects/project-native-runner/studio/api-caller',
    )

    render(<App />)

    expect(await screen.findByText('Studio page: api-runner')).toBeTruthy()
    expect(window.location.pathname).toBe(
      '/projects/project-native-runner/studio/api-runner',
    )
  })

  it('opens the global Engine workspace when no project exists', async () => {
    window.history.replaceState({}, '', '/projects')
    vi.mocked(api.listProjects).mockResolvedValue([] as never)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open Engine test' }))

    expect(await screen.findByText('Global Engine workspace')).toBeTruthy()
    expect(window.location.pathname).toBe('/engine')
  })

  it('preserves a Studio route and retries metadata after backend recovery', async () => {
    let restoreHealth: ((value: { status: string }) => void) | undefined
    vi.mocked(api.health).mockReturnValue(
      new Promise((resolve) => {
        restoreHealth = resolve
      }) as never,
    )
    vi.mocked(api.getProject)
      .mockRejectedValueOnce(new BackendUnavailableError('temporarily unavailable'))
      .mockResolvedValueOnce(project as never)

    render(<App />)

    await waitFor(() => expect(api.getProject).toHaveBeenCalledTimes(1))
    expect(window.location.pathname).toBe('/projects/project-native-runner/studio/api-runner')

    await act(async () => {
      restoreHealth?.({ status: 'ok' })
    })

    await waitFor(() => expect(api.getProject).toHaveBeenCalledTimes(2))
    expect(window.location.pathname).toBe('/projects/project-native-runner/studio/api-runner')
  })

  it('redirects only a canonically missing Studio project', async () => {
    vi.mocked(api.getProject).mockRejectedValueOnce(new ApiError(404, null))

    render(<App />)

    expect(await screen.findByText('Projects page')).toBeTruthy()
    expect(window.location.pathname).toBe('/projects')
  })
})
