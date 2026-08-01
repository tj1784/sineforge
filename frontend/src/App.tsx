import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, BackendUnavailableError, api, type Project } from './api/client'
import { AppShell, type PageId, type ShellView } from './components/AppShell'
import { requestAppNavigation } from './navigationGuard'
import { OperatorContextProvider } from './operator/OperatorContext'
import { Projects } from './pages/Projects'
import { StoryboardStudio } from './pages/StoryboardStudio'
import { ApiRunnerPage } from './studio/pages/ApiRunnerPage'
import type { ProjectWorkflowLane } from './workflowLanes'
import type { PlanningAgent } from './planningAgents'

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
  'sequence-sheet': 'sequence-sheet',
  'api-caller': 'api-runner',
  'api-runner': 'api-runner',
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
  'sequence-sheet': 'sequence-sheet',
  'api-caller': 'api-runner',
  'api-runner': 'api-runner',
  downloads: 'downloads',
  exports: 'exports',
  settings: 'settings',
}

type AppRoute =
  | { kind: 'projects' }
  | { kind: 'new-project' }
  | { kind: 'engine' }
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

function operatorId(prefix: string) {
  const generated =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  return `${prefix}-${generated}`
}

function studioPath(projectId: string, page: PageId): string {
  return `/projects/${encodeURIComponent(projectId)}/studio/${PAGE_TO_ROUTE[page]}`
}

function routePath(route: AppRoute): string {
  if (route.kind === 'projects') return '/projects'
  if (route.kind === 'new-project') return '/projects/new'
  if (route.kind === 'engine') return '/engine'
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

  if (/^\/engine\/?$/.test(pathname)) {
    return { route: { kind: 'engine' } }
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
      if (routeSegment === 'api-caller') {
        return { route, canonicalPath: routePath(route) }
      }
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
  const routeStateRef = useRef(routeState)
  const [backendStatus, setBackendStatus] = useState('checking')
  const [projectName, setProjectName] = useState('Select a project')
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() =>
    routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
      ? routeState.projectId
      : null,
  )
  const [projectCount, setProjectCount] = useState(0)
  const backendUnavailable = backendStatus === 'unavailable'
  const [newProjectWorkflowLane, setNewProjectWorkflowLane] =
    useState<ProjectWorkflowLane | null>(null)
  const [newProjectPlanningAgent, setNewProjectPlanningAgent] =
    useState<PlanningAgent>('qwen')

  useEffect(() => {
    routeStateRef.current = routeState
  }, [routeState])

  const navigateTo = useCallback((route: AppRoute, options?: { replace?: boolean }) => {
    const path = routePath(route)
    const method = options?.replace ? 'replaceState' : 'pushState'
    const proceed = () => {
      if (window.location.pathname !== path) {
        window.history[method](route, '', path)
      }
      routeStateRef.current = route
      setRouteState(route)
    }
    if (window.location.pathname === path) {
      proceed()
      return
    }
    requestAppNavigation(proceed)
  }, [])

  const startNewProject = useCallback(
    (
      workflowLane: ProjectWorkflowLane | null = null,
      planningAgent: PlanningAgent = 'qwen',
    ) => {
      setNewProjectWorkflowLane(workflowLane)
      setNewProjectPlanningAgent(planningAgent)
      navigateTo({ kind: 'new-project' })
    },
    [navigateTo],
  )

  const navigateStudio = useCallback(
    (page: PageId) => {
      const projectId =
        routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
          ? routeState.projectId
          : selectedProjectId
      if (!isRealProjectId(projectId)) {
        navigateTo(page === 'api-runner' ? { kind: 'engine' } : { kind: 'projects' })
        return
      }
      if (routeState.kind === 'engine' && page === 'api-runner') {
        navigateTo({ kind: 'engine' })
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
      setActiveProject(null)
      setSelectedProjectId(projectId)
      if (name) setProjectName(name)
      navigateTo({ kind: 'studio', projectId, page: 'overview' })
    },
    [navigateTo],
  )

  const openProjectPage = useCallback(
    (projectId: string, name: string, page: PageId) => {
      if (!isRealProjectId(projectId)) return
      setActiveProject(null)
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
    const onPopState = () => {
      const parsed = readAppRoute()
      const targetPath = parsed.canonicalPath ?? routePath(parsed.route)
      const currentRoute = routeStateRef.current
      const proceed = () => {
        if (window.location.pathname !== targetPath) {
          window.history.replaceState(parsed.route, '', targetPath)
        }
        routeStateRef.current = parsed.route
        setRouteState(parsed.route)
      }
      if (!requestAppNavigation(proceed)) {
        window.history.pushState(currentRoute, '', routePath(currentRoute))
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    // Invalid / legacy studio ids are already rewritten by readAppRoute / isRealProjectId guards.
    if (routeState.kind !== 'studio' || !isRealProjectId(routeState.projectId)) return
    if (backendUnavailable) return

    let active = true
    void api
      .getProject(routeState.projectId)
      .then((project) => {
        if (active) {
          setActiveProject(project)
          setProjectName(project.name)
          setSelectedProjectId(project.id)
        }
      })
      .catch((error: unknown) => {
        if (!active) return
        if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
          setActiveProject(null)
          setProjectName('Selected project')
          // Only a canonical missing/deleted response invalidates the Studio URL.
          navigateTo({ kind: 'projects' }, { replace: true })
          return
        }
        if (error instanceof BackendUnavailableError) {
          setBackendStatus('unavailable')
        }
      })
    return () => {
      active = false
    }
  }, [backendUnavailable, routeState, navigateTo])

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0 })
  }, [routeState])

  useEffect(() => {
    const initial = window.setTimeout(() => void refreshBackendStatus(), 0)
    const timer = window.setInterval(() => {
      void refreshBackendStatus()
    }, backendUnavailable ? 2_000 : 10_000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [backendUnavailable, refreshBackendStatus])

  const shellView: ShellView =
    routeState.kind === 'studio'
      ? 'studio'
      : routeState.kind === 'engine'
        ? 'engine'
        : routeState.kind === 'new-project'
          ? 'new-project'
          : 'projects'
  const activePage =
    routeState.kind === 'studio'
      ? routeState.page
      : routeState.kind === 'engine'
        ? 'api-runner'
        : 'overview'
  const activeProjectId =
    routeState.kind === 'studio' && isRealProjectId(routeState.projectId)
      ? routeState.projectId
      : selectedProjectId ?? ''
  const activeProjectName = projectName
  const activeProjectWorkflowLane =
    routeState.kind === 'studio' && activeProject?.id === routeState.projectId
      ? activeProject.workflow_lane
      : null
  const currentPath = routePath(routeState)
  const pageViewId = useMemo(() => operatorId('pageview'), [currentPath])
  const operatorBaseContext = useMemo(
    () => ({
      contextVersion: 1,
      capturedAt: new Date().toISOString(),
      routeId:
        routeState.kind === 'studio'
          ? `studio.${routeState.page}`
          : routeState.kind,
      pathname: currentPath,
      pageViewId,
      pageTitle:
        routeState.kind === 'studio'
          ? `${activeProjectName} · ${activePage}`
          : routeState.kind === 'engine'
            ? 'Sineforge Engine'
            : routeState.kind === 'new-project'
              ? 'Create Project'
              : 'Projects',
      domain: routeState.kind === 'engine' ? 'engine' : routeState.kind === 'studio' ? 'studio' : 'workspace',
      tenantId: 'local-workspace',
      projectId: routeState.kind === 'studio' ? routeState.projectId : null,
      projectVersion: activeProject?.created_at ?? null,
      recordType: routeState.kind === 'studio' ? 'project' : null,
      recordId: routeState.kind === 'studio' ? routeState.projectId : null,
      recordVersion: activeProject?.created_at ?? null,
      parentRefs: [],
      selectedRefs:
        routeState.kind === 'studio'
          ? [{ type: 'project', id: routeState.projectId, version: activeProject?.created_at ?? null }]
          : [],
      activeTab: routeState.kind === 'studio' ? routeState.page : routeState.kind,
      activePanel: null,
      filters: {},
      mode: 'view' as const,
      dirty: false,
      capabilities: ['context.get_current', 'context.refresh', 'project.search'],
      correlationId: operatorId('operator-correlation'),
    }),
    [
      activePage,
      activeProject?.created_at,
      activeProjectName,
      currentPath,
      pageViewId,
      routeState,
    ],
  )

  return (
    <OperatorContextProvider baseContext={operatorBaseContext}>
      <AppShell
        activePage={activePage}
        backendStatus={backendStatus}
        projectId={activeProjectId}
        projectName={activeProjectName}
        workflowLane={activeProjectWorkflowLane}
        projectCount={projectCount}
        view={shellView}
        onNavigate={navigateStudio}
        onOpenProjects={() => navigateTo({ kind: 'projects' })}
        onCreateProject={() => startNewProject()}
        onRefreshStatus={() => void refreshBackendStatus()}
      >
        {routeState.kind === 'projects' ? (
          <Projects
            key="projects-list"
            mode="list"
            currentProjectId={selectedProjectId}
            onCreateNew={() => startNewProject()}
            onContinueAgentless={(planningAgent) =>
              startNewProject('agentless', planningAgent)
            }
            onOpenProject={openProject}
            onOpenProjectPage={openProjectPage}
            onProjectsLoaded={handleProjectsLoaded}
            onNavigateStudio={(page) => {
              if (!isRealProjectId(selectedProjectId)) {
                if (page === 'api-runner') navigateTo({ kind: 'engine' })
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
            initialWorkflowLane={newProjectWorkflowLane}
            initialPlanningAgent={newProjectPlanningAgent}
            onBackToProjects={() => navigateTo({ kind: 'projects' })}
            onOpenProject={openProject}
          />
        ) : null}
        {routeState.kind === 'studio' && isRealProjectId(routeState.projectId) ? (
          <StoryboardStudio
            key={routeState.projectId}
            page={routeState.page}
            projectId={routeState.projectId}
            workflowLane={activeProjectWorkflowLane}
            backendStatus={backendStatus}
            onNavigate={navigateStudio}
          />
        ) : null}
        {routeState.kind === 'engine' ? <ApiRunnerPage /> : null}
      </AppShell>
    </OperatorContextProvider>
  )
}

export default App
