import type { ReactNode } from 'react'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api/client'
import App from './App'
import {
  APP_NAVIGATION_REQUEST_EVENT,
  type AppNavigationRequestDetail,
} from './navigationGuard'

vi.mock('./api/client', () => ({
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
  Projects: () => <div>Projects page</div>,
}))

vi.mock('./pages/StoryboardStudio', () => ({
  StoryboardStudio: ({ page }: { page: string }) => <div>Studio page: {page}</div>,
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
})
