import { useEffect, useId, useState, type ReactNode } from 'react'
import { api, type LMStudioModelCatalog, type ManagedEngineStatus } from '../api/client'
import type { ProjectWorkflowLane } from '../workflowLanes'
import {
  getShellTopbarActions,
  subscribeShellTopbarActions,
  type ShellTopbarActions,
} from './shellTopbarActions'

export type PageId =
  | 'overview'
  | 'storyboard'
  | 'story'
  | 'characters'
  | 'voices'
  | 'images'
  | 'routing'
  | 'workflows'
  | 'sequence-sheet'
  | 'api-caller'
  | 'api-runner'
  | 'downloads'
  | 'exports'
  | 'settings'

export type ShellView = 'projects' | 'new-project' | 'studio' | 'engine'

/** Exact Gold Sites `IconName` subset used by AppShell chrome. */
type ShellIconName =
  | 'grid'
  | 'film'
  | 'book'
  | 'people'
  | 'mic'
  | 'cpu'
  | 'layers'
  | 'download'
  | 'settings'
  | 'play'
  | 'check'
  | 'chevron'
  | 'plus'
  | 'image'
  | 'menu'
  | 'folder'
  | 'arrow'
  | 'more'

const navItems: { id: PageId; label: string; icon: ShellIconName }[] = [
  { id: 'overview', label: 'Overview', icon: 'grid' },
  { id: 'storyboard', label: 'Storyboard', icon: 'film' },
  { id: 'story', label: 'Story & chapters', icon: 'book' },
  { id: 'characters', label: 'Characters', icon: 'people' },
  { id: 'voices', label: 'Voices', icon: 'mic' },
  { id: 'images', label: 'Starting images', icon: 'image' },
  { id: 'routing', label: 'Model routing', icon: 'cpu' },
  { id: 'workflows', label: 'Workflows', icon: 'layers' },
  { id: 'sequence-sheet', label: 'Sequence Sheet', icon: 'film' },
  { id: 'api-runner', label: 'API Runner', icon: 'play' },
  { id: 'downloads', label: 'Downloads', icon: 'download' },
  { id: 'exports', label: 'Exports', icon: 'download' },
]

const labels: Record<PageId | 'projects' | 'new-project', string> = {
  projects: 'Projects',
  'new-project': 'Create Project',
  overview: 'Overview',
  storyboard: 'Storyboard',
  story: 'Story & Chapters',
  characters: 'Characters',
  voices: 'Voices',
  images: 'Starting Images',
  routing: 'Model Routing',
  workflows: 'Workflows',
  'sequence-sheet': 'Sequence Sheet',
  'api-caller': 'API Caller',
  'api-runner': 'API Runner',
  downloads: 'Downloads',
  exports: 'Exports',
  settings: 'Project Settings',
}

type AppShellProps = {
  activePage: PageId
  backendStatus: string
  projectId: string
  projectName: string
  workflowLane: ProjectWorkflowLane | null
  projectCount: number
  view: ShellView
  onNavigate: (page: PageId) => void
  onOpenProjects: () => void
  onCreateProject: () => void
  onRefreshStatus?: () => void
  children: ReactNode
}

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || 'CF'
  )
}

function formatModelSize(sizeBytes: number | null) {
  if (!sizeBytes) return null
  return `${(sizeBytes / 1024 ** 3).toFixed(1)} GB`
}

/**
 * Pixel-identical Gold Sites icon strokes (`CineForge-Storyboard-Studio-v2/components/ui.tsx`).
 * strokeWidth 1.7 / round caps — theme targets `sidebar nav button.active svg`.
 */
function Icon({ name, size = 18 }: { name: ShellIconName; size?: number }) {
  const paths: Record<ShellIconName, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    film: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M7 5v14M17 5v14M3 9h4M17 9h4M3 15h4M17 15h4" />
      </>
    ),
    book: (
      <>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5z" />
        <path d="M8 7h8M8 11h6" />
      </>
    ),
    people: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.2a3 3 0 0 1 0 5.6M17 14c2.3.7 4 2.8 4 5.4" />
      </>
    ),
    mic: (
      <>
        <rect x="9" y="2" width="6" height="12" rx="3" />
        <path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8" />
      </>
    ),
    cpu: (
      <>
        <rect x="5" y="5" width="14" height="14" rx="2" />
        <rect x="9" y="9" width="6" height="6" rx="1" />
        <path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M19 9h4M1 15h4M19 15h4" />
      </>
    ),
    layers: <path d="m12 2 9 5-9 5-9-5zM3 12l9 5 9-5M3 17l9 5 9-5" />,
    download: <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />,
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7z" />,
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    image: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="8.5" cy="9" r="1.5" />
        <path d="m21 15-5-5L5 20" />
      </>
    ),
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    folder: <path d="M3 6h7l2 2h9v11H3z" />,
    arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
    more: (
      <>
        <circle cx="5" cy="12" r="1" fill="currentColor" />
        <circle cx="12" cy="12" r="1" fill="currentColor" />
        <circle cx="19" cy="12" r="1" fill="currentColor" />
      </>
    ),
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

export function AppShell({
  activePage,
  backendStatus,
  projectId,
  projectName,
  workflowLane,
  projectCount,
  view,
  onNavigate,
  onOpenProjects,
  onCreateProject,
  onRefreshStatus,
  children,
}: AppShellProps) {
  const [mobile, setMobile] = useState(false)
  const [projectMenu, setProjectMenu] = useState(false)
  const [profile, setProfile] = useState(false)
  const [runtime, setRuntime] = useState(false)
  const [modelCatalog, setModelCatalog] = useState<LMStudioModelCatalog | null>(null)
  const [modelCatalogLoading, setModelCatalogLoading] = useState(true)
  const [modelChanging, setModelChanging] = useState(false)
  const [modelError, setModelError] = useState<string | null>(null)
  const [engineStatus, setEngineStatus] = useState<ManagedEngineStatus | null>(null)
  const [engineLoading, setEngineLoading] = useState(false)
  const [engineError, setEngineError] = useState<string | null>(null)
  const [engineRefresh, setEngineRefresh] = useState(0)
  const [shellActions, setShellActions] = useState<ShellTopbarActions>(() => getShellTopbarActions())
  const navId = useId()
  const isStudio = view === 'studio'
  const isEngine = view === 'engine'
  const isAgentless = isStudio && workflowLane === 'agentless'
  const visibleNavItems = isEngine
    ? navItems.filter((item) => item.id === 'api-runner')
    : isAgentless
    ? navItems.filter(
        (item) => !['images', 'routing', 'api-caller', 'api-runner'].includes(item.id),
      )
    : navItems
  const projectInitials = initials(projectName)
  const activeLabel =
    view === 'projects'
      ? labels.projects
      : view === 'new-project'
        ? labels['new-project']
        : labels[activePage]
  const runtimeLabel = 'Sineforge engine'
  const runtimeStatusDetail =
    backendStatus === 'ok' || backendStatus === 'ready'
      ? 'Local backend ok'
      : `Local backend ${backendStatus}`
  const engineStatusDetail = engineLoading
    ? 'Checking bundled engine…'
    : engineStatus?.ready
      ? `BlokeyUI ready${engineStatus.pid ? ` · PID ${engineStatus.pid}` : ''}`
      : engineError ?? engineStatus?.last_error ?? `Bundled engine ${engineStatus?.status ?? 'unavailable'}`
  const activeModel = modelCatalog?.models.find(
    (model) =>
      model.selected ||
      model.model_id === modelCatalog.active_model_id ||
      model.loaded_instance_ids.includes(modelCatalog.active_model_id),
  )

  useEffect(() => subscribeShellTopbarActions(() => setShellActions(getShellTopbarActions())), [])

  useEffect(() => {
    let cancelled = false
    api
      .listLmStudioModels()
      .then((catalog) => {
        if (!cancelled) {
          setModelCatalog(catalog)
          setModelError(null)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setModelError(error instanceof Error ? error.message : 'LM Studio model list is unavailable.')
        }
      })
      .finally(() => {
        if (!cancelled) setModelCatalogLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [runtime])

  useEffect(() => {
    if (!runtime) return
    let cancelled = false
    let requesting = false
    const readEngineStatus = () => {
      if (requesting) return
      requesting = true
      void api.engineStatus()
      .then((status) => {
        if (!cancelled) {
          setEngineStatus(status)
          setEngineError(null)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setEngineStatus(null)
          setEngineError(
            error instanceof Error ? error.message : 'Bundled engine status is unavailable.',
          )
        }
      })
      .finally(() => {
        requesting = false
        if (!cancelled) setEngineLoading(false)
      })
    }
    readEngineStatus()
    const timer = window.setInterval(readEngineStatus, 3_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [engineRefresh, runtime])

  useEffect(() => {
    if (!mobile && !projectMenu && !profile && !runtime) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobile(false)
        setProjectMenu(false)
        setProfile(false)
        setRuntime(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobile, profile, projectMenu, runtime])

  useEffect(() => {
    if (!projectMenu && !profile && !runtime) return
    const closeOutside = (event: PointerEvent) => {
      const target = event.target
      if (target instanceof Element && target.closest('[data-shell-popover-root]')) return
      setProjectMenu(false)
      setProfile(false)
      setRuntime(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [profile, projectMenu, runtime])

  useEffect(() => {
    const breakpoint = window.matchMedia('(max-width: 900px)')
    const closeAtDesktop = () => {
      if (!breakpoint.matches) setMobile(false)
    }
    breakpoint.addEventListener('change', closeAtDesktop)
    closeAtDesktop()
    return () => breakpoint.removeEventListener('change', closeAtDesktop)
  }, [])

  const goPage = (page: PageId) => {
    onNavigate(page)
    setMobile(false)
    setProjectMenu(false)
    setProfile(false)
    setRuntime(false)
  }

  const goWorkspace = (action: () => void) => {
    action()
    setMobile(false)
    setProjectMenu(false)
    setProfile(false)
    setRuntime(false)
  }

  const selectPlanningModel = async (modelId: string) => {
    if (
      !modelCatalog ||
      (modelId === modelCatalog.active_model_id && activeModel?.loaded)
    ) {
      return
    }
    setModelChanging(true)
    setModelError(null)
    try {
      await api.activateLmStudioModel(modelId)
      const refreshed = await api.listLmStudioModels()
      setModelCatalog(refreshed)
      onRefreshStatus?.()
    } catch (error) {
      setModelError(
        error instanceof Error ? error.message : 'LM Studio could not load the selected model.',
      )
    } finally {
      setModelChanging(false)
    }
  }

  return (
    <div className="app-shell">
      <a className="skip-link sr-only" href="#main-content">
        Skip to main content
      </a>

      <aside
        id="primary-navigation"
        className={`sidebar ${mobile ? 'mobile-open' : ''}`}
        aria-label="Primary navigation"
      >
        <button type="button" className="brand" onClick={() => goWorkspace(onOpenProjects)}>
          <span className="brand-mark" aria-hidden="true">
            <Icon name="play" size={15} />
          </span>
          <span>CineForge Studio</span>
        </button>

        <section className="sidebar-workspace-section" aria-label="Workspace navigation">
          <p className="nav-label">WORKSPACE</p>
          <nav className="workspace-nav">
            <button
              type="button"
              className={view === 'projects' ? 'active' : ''}
              onClick={() => goWorkspace(onOpenProjects)}
            >
              <Icon name="folder" size={18} />
              <span>Projects</span>
              <em>{projectCount}</em>
            </button>
          </nav>
        </section>

        <div className="project-switcher" data-shell-popover-root>
          <button
            type="button"
            className="project-switch"
            title={projectId}
            aria-expanded={projectMenu}
            aria-haspopup="menu"
            onClick={() => {
              setProjectMenu((open) => !open)
              setProfile(false)
              setRuntime(false)
            }}
          >
            <span className="project-thumb">{projectInitials}</span>
            <span>
              <strong>{projectName}</strong>
              <small>
                {projectId || projectName !== 'Select a project'
                  ? isAgentless
                    ? 'Local agents · deterministic production'
                    : 'Seven-phase production plan'
                  : 'Select a project'}
              </small>
            </span>
            <b aria-hidden="true">⌄</b>
          </button>
          {projectMenu ? (
            <div className="popover project-pop" role="menu">
              <button type="button" role="menuitem" onClick={() => goWorkspace(onOpenProjects)}>
                <Icon name="folder" size={18} />
                <span>
                  <b>All projects</b>
                  <small>{projectCount} in this workspace</small>
                </span>
                <Icon name="arrow" size={16} />
              </button>
              <button type="button" role="menuitem" onClick={() => setProjectMenu(false)}>
                <span className="project-thumb">{projectInitials}</span>
                <span>
                  <b>{projectName}</b>
                  <small>Current project</small>
                </span>
                <Icon name="check" size={16} />
              </button>
              <button type="button" role="menuitem" onClick={() => goWorkspace(onCreateProject)}>
                <Icon name="plus" size={18} />
                <span>
                  <b>New project</b>
                  <small>Guided three-step setup</small>
                </span>
                <Icon name="arrow" size={16} />
              </button>
            </div>
          ) : null}
        </div>

        <section className="sidebar-project-section" aria-label="Current project navigation">
          <p className="nav-label project-nav-label">{isEngine ? 'ENGINE' : 'PRODUCTION'}</p>
          <nav id={navId} className="project-nav">
            {visibleNavItems.map((item) => {
              const active = (isStudio || isEngine) && item.id === activePage
              return (
                <button
                  type="button"
                  key={item.id}
                  className={active ? 'active' : ''}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => goPage(item.id)}
                >
                  <Icon name={item.icon} size={18} />
                  <span>
                    {isAgentless && item.id === 'sequence-sheet'
                      ? 'Agentless scene reset'
                      : item.label}
                  </span>
                </button>
              )
            })}
          </nav>
        </section>

        <div className="sidebar-bottom" data-shell-popover-root>
          <button
            type="button"
            className={isStudio && activePage === 'settings' ? 'active' : ''}
            disabled={!isStudio}
            onClick={() => goPage('settings')}
          >
            <Icon name="settings" size={18} />
            <span>Project settings</span>
          </button>

          <button
            type="button"
            className="gpu"
            aria-expanded={runtime}
            aria-controls="runtime-preview-popover"
            aria-haspopup="dialog"
            onClick={() => {
              const opening = !runtime
              setRuntime(opening)
              if (opening) {
                setEngineLoading(true)
                setEngineError(null)
              }
              setProfile(false)
              setProjectMenu(false)
            }}
          >
            <i aria-hidden="true" />
            <span>
              <strong>{runtimeLabel}</strong>
              <small>{isAgentless ? 'LM Studio · bundled engine · JSON manifests' : 'BlokeyUI engine · local agents'}</small>
            </span>
          </button>
          {runtime ? (
            <div
              id="runtime-preview-popover"
              className="popover runtime-pop"
              role="dialog"
              aria-label="Preview runtime status"
            >
              <b>Sineforge runtime</b>
              <p role="status" aria-live="polite">
                Sineforge owns the bundled BlokeyUI process and sends validated workflows to
                its ComfyUI engine. {engineStatusDetail}. Backend: {runtimeStatusDetail}.
              </p>
              <div className="runtime-model-toggle">
                <label htmlFor="runtime-planning-model">
                  <span>Planning model</span>
                  <small>
                    {activeModel?.loaded
                      ? 'Loaded in LM Studio'
                      : modelCatalog?.reachable
                        ? 'Select to load'
                        : 'Start LM Studio to switch'}
                  </small>
                </label>
                <select
                  id="runtime-planning-model"
                  aria-label="Active LM Studio planning model"
                  value={modelCatalog?.active_model_id ?? ''}
                  disabled={
                    modelCatalogLoading ||
                    modelChanging ||
                    !modelCatalog?.reachable
                  }
                  onChange={(event) => void selectPlanningModel(event.target.value)}
                >
                  {modelCatalogLoading && !modelCatalog ? (
                    <option value="">Loading local models…</option>
                  ) : null}
                  {modelCatalog?.models.map((model) => (
                    <option
                      key={`${model.key}:${model.model_id}`}
                      value={model.model_id}
                      disabled={!model.installed}
                    >
                      {model.display_name}
                      {model.loaded ? ' · loaded' : ''}
                    </option>
                  ))}
                </select>
                {activeModel ? (
                  <p className="runtime-model-meta" title={activeModel.filename ?? undefined}>
                    {[activeModel.quantization, formatModelSize(activeModel.size_bytes)]
                      .filter(Boolean)
                      .join(' · ')}
                    {modelChanging ? ' · Loading model…' : ''}
                  </p>
                ) : null}
                {modelError || modelCatalog?.error ? (
                  <p className="runtime-model-error" role="status">
                    {modelError ?? 'LM Studio is offline. The saved selection is unchanged.'}
                  </p>
                ) : null}
              </div>
              {isAgentless ? (
                <p className="notice">
                  Local LM Studio planning is allowed and hosted/API agents are blocked.
                  Rendering stays deterministic and disabled until both exact JSON
                  scene-reset workflows pass admission.
                </p>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  setRuntime(false)
                  goPage('api-runner')
                }}
              >
                Open Engine workspace
                <Icon name="arrow" size={14} />
              </button>
              {onRefreshStatus ? (
                <button
                  type="button"
                  onClick={() => {
                    setEngineLoading(true)
                    setEngineError(null)
                    setEngineRefresh((value) => value + 1)
                    onRefreshStatus()
                  }}
                >
                  Refresh status
                  <Icon name="arrow" size={14} />
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  setRuntime(false)
                  goPage('settings')
                }}
              >
                Open project settings
                <Icon name="arrow" size={14} />
              </button>
            </div>
          ) : null}

          <button
            type="button"
            className="user"
            aria-expanded={profile}
            aria-controls="profile-popover"
            aria-haspopup="menu"
            onClick={() => {
              setProfile((open) => !open)
              setRuntime(false)
              setProjectMenu(false)
            }}
          >
            <span>RP</span>
            <span>
              <strong>Robert</strong>
              <small>Producer</small>
            </span>
            <Icon name="more" size={18} />
          </button>
          {profile ? (
            <div id="profile-popover" className="popover profile-pop" role="menu">
              <b>Robert Padilla</b>
              <small>Project owner · Producer</small>
              <button type="button" role="menuitem" onClick={() => goPage('settings')}>
                Project settings
              </button>
            </div>
          ) : null}
        </div>
      </aside>

      {mobile ? (
        <button
          type="button"
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      ) : null}

      <section className="workspace">
        <header className="topbar">
          <div className="top-left">
            <button
              type="button"
              className="mobile-menu"
              aria-label="Toggle navigation"
              aria-expanded={mobile}
              aria-controls="primary-navigation"
              onClick={() => setMobile((open) => !open)}
            >
              <Icon name="menu" size={18} />
            </button>
            {/* Sites topbar crumbs: Projects › Project › Page · PHASE A */}
            <div className="crumbs" aria-label="Breadcrumb">
              {view === 'projects' ? (
                <>
                  <strong>Projects</strong>
                  <span className="workspace-chip">WORKSPACE</span>
                </>
              ) : null}
              {view === 'new-project' ? (
                <>
                  <button type="button" onClick={() => goWorkspace(onOpenProjects)}>
                    Projects
                  </button>
                  <Icon name="chevron" size={13} />
                  <b>Create project</b>
                </>
              ) : null}
              {isStudio ? (
                <>
                  <button type="button" onClick={() => goWorkspace(onOpenProjects)}>
                    Projects
                  </button>
                  <Icon name="chevron" size={13} />
                  <strong title={projectId}>{projectName}</strong>
                  <Icon name="chevron" size={13} />
                  <b>{activeLabel}</b>
                  <span
                    className="phase"
                    aria-label={isAgentless ? 'Local-agent deterministic workflow' : 'Seven production phases'}
                  >
                    {isAgentless ? 'AGENTLESS' : '7 PHASES'}
                  </span>
                </>
              ) : null}
              {isEngine ? (
                <>
                  <button type="button" onClick={() => goWorkspace(onOpenProjects)}>
                    Projects
                  </button>
                  <Icon name="chevron" size={13} />
                  <b>Engine</b>
                  <span className="phase" aria-label="Bundled local engine workspace">
                    LOCAL
                  </span>
                </>
              ) : null}
            </div>
          </div>
          {/* Only real actions are presented; project fields persist through their API forms. */}
          <div className="top-actions">
            {isStudio ? (
              <label
                className="shell-model-toggle"
                title={
                  modelError ??
                  modelCatalog?.error ??
                  activeModel?.filename ??
                  'Choose the LM Studio planning model'
                }
              >
                <Icon name="cpu" size={15} />
                <select
                  aria-label="Active LM Studio planning model"
                  value={modelCatalog?.active_model_id ?? ''}
                  disabled={
                    modelCatalogLoading ||
                    modelChanging ||
                    !modelCatalog?.reachable
                  }
                  onChange={(event) => void selectPlanningModel(event.target.value)}
                >
                  {!modelCatalog ? (
                    <option value="">Loading local models…</option>
                  ) : null}
                  {modelCatalog?.models.map((model) => (
                    <option
                      key={`top:${model.key}:${model.model_id}`}
                      value={model.model_id}
                      disabled={!model.installed}
                    >
                      {model.display_name}
                      {model.loaded ? ' · loaded' : ''}
                    </option>
                  ))}
                </select>
                <i
                  className={
                    modelChanging
                      ? 'loading'
                      : activeModel?.loaded
                        ? 'loaded'
                        : 'offline'
                  }
                  aria-hidden="true"
                />
              </label>
            ) : null}
            {view === 'projects' ? (
              <button type="button" className="btn primary" onClick={onCreateProject}>
                <Icon name="plus" size={15} />
                <span>New project</span>
              </button>
            ) : null}
            {isStudio ? (
              <button
                type="button"
                className="btn primary"
                disabled={shellActions.canPreview === false}
                title="Timing prototype only — no video rendering"
                onClick={() => shellActions.previewAnimatic?.()}
              >
                <Icon name="play" size={15} />
                <span>Preview animatic</span>
              </button>
            ) : null}
          </div>
        </header>

        <main id="main-content" className="page-scroll" tabIndex={-1}>
          {children}
        </main>
      </section>
    </div>
  )
}
