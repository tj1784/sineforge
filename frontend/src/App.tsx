import { useCallback, useEffect, useState } from 'react'
import { api, type Project } from './api/client'
import { AppShell, type PageId, type ShellView } from './components/AppShell'
import { Projects } from './pages/Projects'
import { StoryboardStudio } from './pages/StoryboardStudio'

/** Legacy slug only for URL rewrite — never use as an API project id. */
const LEGACY_PROJECT_SLUG = 'a-new-journey'

const PAGE_TO_ROUTE: Record<PageId, string> = {
  overview: 'overview',
  storyboard: 'storyboard',
  story: 'story',
  characters: 'characters',
  voices: 'voices',
  images: 'starting-images',
  routing: 'model-routing',
  workflows: 'workflows',
  'api-caller': 'api-caller',
  downloads: 'downloads',
  exports: 'exports',
  settings: 'settings',
}

const ROUTE_TO_PAGE: Record<string, PageId> = {
  overview: 'overview',
  storyboard: 'storyboard',
  story: 'story',
  characters: 'characters',
  voices: 'voices',
  'starting-images': 'images',
  images: 'images',
  'model-routing': 'routing',
  routing: 'routing',
  workflows: 'workflows',
  'api-caller': 'api-caller',
  downloads: 'downloads',
  exports: 'exports',
  settings: 'settings',
}

type AppRoute =
  | { kind: 'projects' }
  | { kind: 'new-project' }
  | { kind: 'studio'; projectId: string; page: PageId }

type ParsedRoute = {
  route: AppRoute
  canonicalPath?: string
}

function isRealProjectId(projectId: string | null | undefined): projectId is string {
  if (!projectId) return false
  if (projectId === LEGACY_PROJECT_SLUG) return false
  // UUIDs (any version) or other non-slug ids from the API
  return projectId.length >= 8 && !projectId.includes(' ')
}

function normalizeBackendStatus(value: string | undefined): string {
  const status = (value ?? 'unknown').toLowerCase()
  if (status === 'ok' || status === 'healthy' || status === 'up' || status === 'ready') return 'ok'
  if (status === 'degraded' || status === 'partial') return 'degraded'
  if (status === 'disabled') return 'disabled'
  if (status === 'checking' || status === 'loading') return 'checking'
  return 'unavailable'
}

function studioPath(projectId: string, page: PageId): string {
  return `/projects/${encodeURIComponent(projectId)}/studio/${PAGE_TO_ROUTE[page]}`
}

function routePath(route: AppRoute): string {
  if (route.kind === 'projects') return '/projects'
  if (route.kind === 'new-project') return '/projects/new'
  return studioPath(route.projectId, route.page)
}

function readAppRoute(pathname = window.location.pathname): ParsedRoute {
  if (pathname === '/' || pathname === '') {
    return { route: { kind: 'projects' }, canonicalPath: '/projects' }
  }

  if (/^\/projects\/?$/.test(pathname)) {
    return { route: { kind: 'projects' } }
  }

  if (/^\/projects\/new\/?$/.test(pathname)) {
    return { route: { kind: 'new-project' } }
  }

  const studioMatch = pathname.match(/^\/projects\/([^/]+)\/studio\/([^/]+)\/?$/)
  if (studioMatch) {
    const [, encodedProjectId, routeSegment] = studioMatch
    try {
      const projectId = decodeURIComponent(encodedProjectId || '')
      const page = ROUTE_TO_PAGE[routeSegment] ?? 'overview'
      // Legacy slug URLs cannot hit the API — bounce to projects until a real id is chosen.
      if (!isRealProjectId(projectId)) {
        return { route: { kind: 'projects' }, canonicalPath: '/projects' }
      }
      const route: AppRoute = { kind: 'studio', projectId, page }
      return ROUTE_TO_PAGE[routeSegment] ? { route } : { route, canonicalPath: routePath(route) }
    } catch {
      return { route: { kind: 'projects' }, canonicalPath: '/projects' }
    }
  }

  return { route: { kind: 'projects' }, canonicalPath: '/projects' }
}

function App() {
  const [routeState, setRouteState] = useState<AppRoute>(() => {
    const parsed = readAppRoute()
    // Canonicalize legacy / invalid studio URLs during first paint — no effect setState.
    if (parsed.canonicalPath && window.location.pathname !== parsed.canonicalPath) {
      window.history.replaceState(parsed.route, '', parsed.canonicalPath)
    }
    return parsed.route
  })
  const [backendStatus, setBackendStatus] = useState('checking')
  const [projectName, setProjectName] = useState('Select a project')
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() =>
    routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
      ? routeState.projectId
      : null,
  )
  const [projectCount, setProjectCount] = useState(0)

  const navigateTo = useCallback((route: AppRoute, options?: { replace?: boolean }) => {
    const path = routePath(route)
    const method = options?.replace ? 'replaceState' : 'pushState'
    if (window.location.pathname !== path) {
      window.history[method](route, '', path)
    }
    setRouteState(route)
  }, [])

  const navigateStudio = useCallback(
    (page: PageId) => {
      const projectId =
        routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
          ? routeState.projectId
          : selectedProjectId
      if (!isRealProjectId(projectId)) {
        navigateTo({ kind: 'projects' })
        return
      }
      navigateTo({ kind: 'studio', projectId, page })
    },
    [navigateTo, routeState, selectedProjectId],
  )

  const openProject = useCallback(
    (projectId: string, name?: string) => {
      if (!isRealProjectId(projectId)) {
        navigateTo({ kind: 'projects' })
        return
      }
      setSelectedProjectId(projectId)
      if (name) setProjectName(name)
      navigateTo({ kind: 'studio', projectId, page: 'overview' })
    },
    [navigateTo],
  )

  const openProjectPage = useCallback(
    (projectId: string, name: string, page: PageId) => {
      if (!isRealProjectId(projectId)) return
      setSelectedProjectId(projectId)
      setProjectName(name)
      navigateTo({ kind: 'studio', projectId, page })
    },
    [navigateTo],
  )

  const handleProjectsLoaded = useCallback((projects: Project[]) => {
    setProjectCount(projects.length)
    setSelectedProjectId((currentId) => {
      if (isRealProjectId(currentId) && projects.some((project) => project.id === currentId)) {
        return currentId
      }
      // Prefer Transfiguration for dry-run, else first project — never a slug.
      const preferred =
        projects.find((project) => project.name.toLowerCase().includes('transfiguration')) ??
        projects.find((project) => project.name === 'A New Journey') ??
        projects[0]
      if (!preferred) return null
      setProjectName(preferred.name)
      return preferred.id
    })
  }, [])

  useEffect(() => {
    let active = true
    void api
      .listProjects()
      .then((projects) => {
        if (active) handleProjectsLoaded(projects)
      })
      .catch(() => {
        if (active) setProjectCount(0)
      })
    return () => {
      active = false
    }
  }, [handleProjectsLoaded])

  const refreshBackendStatus = useCallback(async () => {
    try {
      const health = await api.health()
      setBackendStatus(normalizeBackendStatus(health.status))
    } catch {
      setBackendStatus('unavailable')
    }
  }, [])

  useEffect(() => {
    const onPopState = () => setRouteState(readAppRoute().route)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    // Invalid / legacy studio ids are already rewritten by readAppRoute / isRealProjectId guards.
    if (routeState.kind !== 'studio' || !isRealProjectId(routeState.projectId)) return

    let active = true
    void api
      .getProject(routeState.projectId)
      .then((project) => {
        if (active) {
          setProjectName(project.name)
          setSelectedProjectId(project.id)
        }
      })
      .catch(() => {
        if (active) {
          setProjectName('Selected project')
          // Unknown API id — send user back to the project list (async path, not sync-in-effect).
          navigateTo({ kind: 'projects' }, { replace: true })
        }
      })
    return () => {
      active = false
    }
  }, [routeState, navigateTo])

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0 })
  }, [routeState])

  useEffect(() => {
    const initial = window.setTimeout(() => void refreshBackendStatus(), 0)
    const timer = window.setInterval(() => {
      void refreshBackendStatus()
    }, 30_000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [refreshBackendStatus])

  const shellView: ShellView =
    routeState.kind === 'studio' ? 'studio' : routeState.kind === 'new-project' ? 'new-project' : 'projects'
  const activePage = routeState.kind === 'studio' ? routeState.page : 'overview'
  const activeProjectId =
    routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
      ? routeState.projectId
      : selectedProjectId ?? ''
  const activeProjectName = projectName

  return (
    <AppShell
      activePage={activePage}
      backendStatus={backendStatus}
      projectId={activeProjectId}
      projectName={activeProjectName}
      projectCount={projectCount}
      view={shellView}
      onNavigate={navigateStudio}
      onOpenProjects={() => navigateTo({ kind: 'projects' })}
      onCreateProject={() => navigateTo({ kind: 'new-project' })}
      onRefreshStatus={() => void refreshBackendStatus()}
    >
      {routeState.kind === 'projects' ? (
        <Projects
          key="projects-list"
          mode="list"
          currentProjectId={selectedProjectId}
          onCreateNew={() => navigateTo({ kind: 'new-project' })}
          onOpenProject={openProject}
          onOpenProjectPage={openProjectPage}
          onProjectsLoaded={handleProjectsLoaded}
          onNavigateStudio={(page) => {
            if (!isRealProjectId(selectedProjectId)) {
              // No real project selected yet — stay on projects list.
              return
            }
            navigateTo({ kind: 'studio', projectId: selectedProjectId, page })
          }}
        />
      ) : null}
      {routeState.kind === 'new-project' ? (
        <Projects
          key="project-create"
          mode="create"
          onBackToProjects={() => navigateTo({ kind: 'projects' })}
          onOpenProject={openProject}
        />
      ) : null}
      {routeState.kind === 'studio' && isRealProjectId(routeState.projectId) ? (
        <StoryboardStudio
          key={routeState.projectId}
          page={routeState.page}
          projectId={routeState.projectId}
          backendStatus={backendStatus}
          onNavigate={navigateStudio}
        />
      ) : null}
    </AppShell>
  )
}

export default App
