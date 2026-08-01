import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import {
  BackendUnavailableError,
  api,
  type PhaseASnapshot,
  type Project,
  type Story,
  type SulphurProjectWorkspace,
} from '../api/client'
import { projectCoverUrl } from '../studio/mediaUrls'
import { EmptyState, ErrorNotice } from '../components/Cards'
import { PageHeader } from '../components/Page'
import { StudioHomeHero } from '../components/StudioHomeHero'
import { LocalPlanningAgentFieldset } from '../components/LocalPlanningAgentFieldset'
import { ChapterIntakeForm } from '../components/ChapterIntakeForm'
import { ThemeSelector } from '../components/ThemeSelector'
import { makeChapterIntakeDraft, type ChapterIntakeDraft } from '../components/chapterIntake'
import {
  localPlanningAgent,
  type PlanningAgent,
} from '../planningAgents'
import type { PageId } from '../components/AppShell'
import {
  PROJECT_WORKFLOW_LANES,
  projectWorkflowLaneLabel,
  type ProjectWorkflowLane,
} from '../workflowLanes'
import '../workflow-lanes.css'
import {
  EMPTY_BIBLICAL_CONTEXT,
  biblicalContextPayload,
  creativeThemeLabel,
  type BiblicalContextDraft,
  type CreativeThemeId,
} from '../themes'
/* PIXEL: Sites project-card density (also loaded last from main.tsx). */
import '../projects-sites-density.css'

type ProjectsProps = {
  mode?: 'list' | 'create'
  onCreateNew?: () => void
  onBackToProjects?: () => void
  onOpenProject?: (projectId: string, projectName?: string) => void
  onOpenProjectPage?: (projectId: string, projectName: string, page: PageId) => void
  onProjectsLoaded?: (projects: Project[]) => void
  onNavigateStudio?: (page: PageId) => void
  onContinueAgentless?: (planningAgent: PlanningAgent) => void
  initialWorkflowLane?: ProjectWorkflowLane | null
  initialPlanningAgent?: PlanningAgent
  /** Currently selected workspace project — used for the Gold "Current project" cover chip. */
  currentProjectId?: string | null
}

type ProjectSummary = {
  project: Project
  story: Story | null
  snapshot: PhaseASnapshot | null
  status: 'Setup' | 'In progress' | 'Review' | 'Ready' | 'Blocked'
  readiness: number
  openGates: number
}

type SourceMode = 'story' | 'blank' | 'import'

type ProjectDraft = {
  workflowLane: ProjectWorkflowLane | null
  themeId: CreativeThemeId
  themeContext: BiblicalContextDraft
  planningAgent: PlanningAgent
  planningModelId: string | null
  name: string
  description: string
  sourceMode: SourceMode
  baseStory: string
  targetRuntime: number
  requestedChapterCount: number
  chapterIntake: ChapterIntakeDraft[]
  audience: string
  genre: string
  tone: string
  pointOfView: string
  visualStyle: string
  aspectRatio: string
  fps: number
  productionProfileKey: 'ltx_base@1' | 'ltx_base@2' | 'wan_base@1'
  stitchStage: 'phase7_before_audio' | 'phase8_before_foley'
  orchestrationMode: string
  privacy: string
  qualityPreference: string
  costSensitivity: string
  productionNotes: string
  language: string
  narrationDialoguePreference: string
  sourceFidelityConstraints: string
  contentConstraints: string
}

const DEFAULT_CHAPTER_COUNT = 3
const MAX_CHAPTER_COUNT = 50

function makeChapterIntakes(count: number, targetRuntime: number): ChapterIntakeDraft[] {
  const safeCount = Math.max(1, Math.min(MAX_CHAPTER_COUNT, Math.round(count) || 1))
  const targetDurationSec = Math.max(6, Math.round((targetRuntime || 300) / safeCount))
  return Array.from({ length: safeCount }, (_, index) => makeChapterIntakeDraft(index, targetDurationSec))
}

const EMPTY_DRAFT: ProjectDraft = {
  workflowLane: null,
  themeId: 'default',
  themeContext: { ...EMPTY_BIBLICAL_CONTEXT },
  planningAgent: 'qwen',
  planningModelId: null,
  name: '',
  description: '',
  sourceMode: 'story',
  baseStory: '',
  targetRuntime: 300,
  requestedChapterCount: DEFAULT_CHAPTER_COUNT,
  chapterIntake: makeChapterIntakes(DEFAULT_CHAPTER_COUNT, 300),
  audience: 'General audience',
  genre: 'Cinematic narrative',
  tone: 'Grounded, cinematic, human',
  pointOfView: 'Third person',
  visualStyle: 'Photoreal cinematic realism',
  aspectRatio: '16:9',
  fps: 24,
  productionProfileKey: 'ltx_base@1',
  stitchStage: 'phase7_before_audio',
  orchestrationMode: 'Hybrid',
  privacy: 'Prefer local for bulk work',
  qualityPreference: 'Quality weighted',
  costSensitivity: 'Balanced',
  productionNotes: '',
  language: 'English',
  narrationDialoguePreference: 'Non-diegetic narration with intentional silence; dialogue only when the story requires it.',
  sourceFidelityConstraints: '',
  contentConstraints: '',
}

function makeInitialDraft(
  initialWorkflowLane: ProjectWorkflowLane | null,
  initialPlanningAgent: PlanningAgent = 'qwen',
): ProjectDraft {
  return {
    ...EMPTY_DRAFT,
    chapterIntake: EMPTY_DRAFT.chapterIntake.map((chapter) => ({ ...chapter })),
    workflowLane: initialWorkflowLane,
    themeContext: { ...EMPTY_BIBLICAL_CONTEXT },
    planningAgent: initialPlanningAgent,
    ...(initialWorkflowLane === 'agentless'
      ? {
          productionProfileKey: 'ltx_base@2' as const,
          fps: 24,
          orchestrationMode: 'Manual',
          privacy: 'Local only',
        }
      : {}),
  }
}

const SOURCE_OPTIONS: { id: SourceMode; icon: string; title: string; detail: string }[] = [
  { id: 'story', icon: '▱', title: 'Start from a story', detail: 'Paste a script, treatment, narration, or source story.' },
  { id: 'blank', icon: '＋', title: 'Start blank', detail: 'Create the project shell and shape the story inside CineForge.' },
  { id: 'import', icon: '⇧', title: 'Import a package', detail: 'Load a TXT, MD, or JSON source file for intake.' },
]

const OUTPUT_DIMENSIONS: Record<string, { preview: [number, number]; final: [number, number] }> = {
  '16:9': { preview: [1280, 720], final: [1920, 1080] },
  '9:16': { preview: [720, 1280], final: [1080, 1920] },
  '2.39:1': { preview: [1280, 536], final: [1920, 804] },
  '1:1': { preview: [1024, 1024], final: [1920, 1920] },
}

function projectInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'CF'
}

function formatRuntime(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function chapterCode(index: number) {
  return `CH${String(index + 1).padStart(2, '0')}`
}

function formatUpdated(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Recently'
  const now = new Date()
  if (date.toDateString() === now.toDateString()) {
    return `Today · ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  }
  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  })
}

function getProjectStatus(snapshot: PhaseASnapshot | null): ProjectSummary['status'] {
  if (!snapshot) return 'Setup'
  const shots = snapshot.chapters.flatMap((chapter) => chapter.scenes.flatMap((scene) => scene.shots))
  if (shots.some((shot) => shot.production_status === 'blocked' || Boolean(shot.blocked_reason))) return 'Blocked'
  if (snapshot.readiness.ready) return 'Ready'
  if (snapshot.readiness.reasons.some((reason) => reason.blocking)) return 'Review'
  return 'In progress'
}

async function enrichProject(project: Project): Promise<ProjectSummary> {
  try {
    const stories = await api.listStories(project.id)
    const story = stories[0] ?? null
    const snapshot = story ? await api.phaseA(story.id) : null
    const openGates = snapshot
      ? new Set(snapshot.readiness.reasons.filter((reason) => reason.blocking).map((reason) => reason.code)).size
      : 0
    const readiness = snapshot
      ? snapshot.readiness.ready
        ? 100
        : Math.max(0, Math.min(99, Math.round(100 - Math.min(openGates, 10) * 10)))
      : 0
    return { project, story, snapshot, status: getProjectStatus(snapshot), readiness, openGates }
  } catch {
    return { project, story: null, snapshot: null, status: 'Setup', readiness: 0, openGates: 0 }
  }
}


function statusSlug(status: ProjectSummary['status']) {
  // Sites gold-globals status-pill keys use space form (`in progress`).
  // Bridge also accepts hyphen form; density/type come from gold-globals + PIXEL CSS.
  return status.toLowerCase()
}

function phaseLabel(story: Story | null, snapshot: PhaseASnapshot | null) {
  if (!story) return 'Project Setup'
  // Gold Sites labels multi-phase plans this way; single-story Phase A falls back.
  if (snapshot) return 'Seven-phase production plan'
  return 'Storyboard Phase A'
}

function ProjectList({
  onCreateNew,
  onOpenProject,
  onOpenProjectPage,
  onProjectsLoaded,
  onNavigateStudio,
  onContinueAgentless,
  currentProjectId,
}: Pick<ProjectsProps, 'onCreateNew' | 'onOpenProject' | 'onOpenProjectPage' | 'onProjectsLoaded' | 'onNavigateStudio' | 'onContinueAgentless' | 'currentProjectId'>) {
  const [summaries, setSummaries] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [sort, setSort] = useState('Recently created')
  const [loadVersion, setLoadVersion] = useState(0)
  const transportRetryCount = useRef(0)

  const retryNow = useCallback(() => {
    transportRetryCount.current = 0
    setLoadVersion((current) => current + 1)
  }, [])

  const deleteProject = useCallback(async (project: Project) => {
    const confirmed = window.confirm(`Delete "${project.name}" and all of its project data?`)
    if (!confirmed) return
    setError(null)
    try {
      await api.deleteProject(project.id)
      setSummaries((current) => current.filter((summary) => summary.project.id !== project.id))
      setLoadVersion((current) => current + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to delete ${project.name}.`)
    }
  }, [])

  useEffect(() => {
    let active = true
    let retryTimer: number | undefined
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const projects = await api.listProjects()
        if (!active) return
        onProjectsLoaded?.(projects)
        const enriched = await Promise.all(projects.map(enrichProject))
        if (active) {
          transportRetryCount.current = 0
          setSummaries(enriched)
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Unable to load projects.')
          if (err instanceof BackendUnavailableError) {
            const delay = Math.min(2_000 * 2 ** transportRetryCount.current, 15_000)
            transportRetryCount.current += 1
            retryTimer = window.setTimeout(
              () => setLoadVersion((current) => current + 1),
              delay,
            )
          }
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [loadVersion, onProjectsLoaded])

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return summaries
      .filter(({ project }) => `${project.name} ${project.description ?? ''}`.toLowerCase().includes(normalizedQuery))
      .filter((summary) => filter === 'All' || summary.status === filter)
      .sort((left, right) => {
        if (sort === 'Name') return left.project.name.localeCompare(right.project.name)
        if (sort === 'Readiness') return right.readiness - left.readiness
        return new Date(right.project.created_at).getTime() - new Date(left.project.created_at).getTime()
      })
  }, [filter, query, sort, summaries])

  const plannedShots = summaries.reduce(
    (total, summary) => total + (summary.snapshot?.chapters.reduce(
      (chapterTotal, chapter) => chapterTotal + chapter.scenes.reduce(
        (sceneTotal, scene) => sceneTotal + scene.shots.length,
        0,
      ),
      0,
    ) ?? 0),
    0,
  )
  const needReview = summaries.filter((summary) => summary.status === 'Review' || summary.status === 'Blocked').length
  const ready = summaries.filter((summary) => summary.status === 'Ready').length
  const filters = ['All', 'Setup', 'In progress', 'Review', 'Ready']

  return (
    <div className="page projects-page">
      {onNavigateStudio ? (
        <StudioHomeHero
          onCreateProject={async (
            prompt,
            idempotencyKey,
            planningAgent,
            planningModelId,
          ): Promise<SulphurProjectWorkspace> => {
            const workspace = await api.createProjectFromSulphur({
              idempotency_key: idempotencyKey,
              prompt,
              workflow_lane: 'cineforge_studio',
              planning_agent: planningAgent,
              planning_model_id: planningModelId,
              prompt_artifact_format: 'json',
              prompt_schema_version: 'sineforge.local-planning-prompt/v1',
            })
            onOpenProject?.(workspace.project.id, workspace.project.name)
            return workspace
          }}
          onContinueAgentless={(planningAgent) => {
            if (onContinueAgentless) {
              onContinueAgentless(planningAgent)
              return
            }
            onCreateNew?.()
          }}
          onNavigateStudio={(page) => {
            const target =
              summaries.find(({ project }) => project.id === currentProjectId)?.project ??
              summaries[0]?.project
            if (target && onOpenProjectPage) {
              onOpenProjectPage(target.id, target.name, page)
              return
            }
            if (target) {
              onOpenProject?.(target.id, target.name)
              return
            }
            onNavigateStudio(page)
          }}
        />
      ) : (
        <div className="page-title projects-heading">
          <div>
            <span className="eyebrow">CINEFORGE WORKSPACE</span>
            <h1>Projects</h1>
            <p>Create, organize, and continue every production plan from one workspace.</p>
          </div>
          <div className="page-actions">
            <button type="button" className="btn primary" onClick={onCreateNew}>＋ New project</button>
          </div>
        </div>
      )}

      {error ? <ErrorNotice message={error} actionLabel="Retry now" onAction={retryNow} /> : null}

      <section className="projects-summary" aria-label="Project summary">
        <div><span className="summary-icon mint">▣</span><span><small>Total projects</small><b>{summaries.length}</b></span></div>
        <div><span className="summary-icon blue">▤</span><span><small>Planned shots</small><b>{plannedShots}</b></span></div>
        <div><span className="summary-icon amber">△</span><span><small>Need review</small><b>{needReview}</b></span></div>
        <div><span className="summary-icon purple">✓</span><span><small>Production ready</small><b>{ready}</b></span></div>
      </section>

      <div className="projects-toolbar">
        <label className="projects-search">
          <span aria-hidden="true">⌕</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search projects…" aria-label="Search projects" />
          {query ? <button type="button" onClick={() => setQuery('')} aria-label="Clear project search">×</button> : null}
        </label>
        <div className="segmented projects-filter" aria-label="Filter projects">
          {filters.map((item) => (
            <button type="button" key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>
              {item}<span>{item === 'All' ? summaries.length : summaries.filter((summary) => summary.status === item).length}</span>
            </button>
          ))}
        </div>
        <label className="sort-select">
          <span>Sort</span>
          <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort">
            <option>Recently created</option><option>Name</option><option>Readiness</option>
          </select>
        </label>
      </div>

      {loading ? <div className="projects-loading">Loading projects…</div> : null}
      {!loading && filtered.length ? (
        <div className="project-grid">
          {filtered.map(({ project, story, snapshot, status, readiness, openGates }, index) => {
            const chapters = snapshot?.chapters ?? []
            const scenes = chapters.flatMap((chapter) => chapter.scenes)
            const shots = scenes.flatMap((scene) => scene.shots)
            const characters = snapshot?.characters ?? []
            const coverUrl = projectCoverUrl({
              projectId: project.id,
              projectName: project.name,
              storyTitle: story?.title,
              shotTitles: shots.map((shot) => shot.title),
              firstAssetId:
                shots.find((shot) => Boolean(shot.starting_image_asset_id))?.starting_image_asset_id ?? null,
            })
            const open = () => onOpenProject?.(project.id, project.name)
            const isCurrent = Boolean(currentProjectId) && currentProjectId === project.id
            return (
              <article className={isCurrent ? 'project-card current' : 'project-card'} key={project.id}>
                <button type="button" className={`project-cover project-cover-${index % 6}`} onClick={open} aria-label={`Open ${project.name}`}>
                  {coverUrl ? (
                    <img className="project-cover-image" src={coverUrl} alt="" loading="lazy" decoding="async" />
                  ) : null}
                  <span className="cover-grid" /><span className="cover-orb orb-a" /><span className="cover-orb orb-b" />
                  <span className="cover-initials">{projectInitials(project.name)}</span>
                  {isCurrent ? <em><i />Current project</em> : null}
                  <span className="status-pill" data-status={statusSlug(status)}>{status}</span>
                </button>
                <div className="project-card-body">
                  <div className="project-card-title">
                    <button type="button" onClick={open}><h2>{project.name}</h2><p>{project.description || 'A CineForge production plan.'}</p></button>
                  </div>
                  <div className="project-card-actions">
                    <button
                      type="button"
                      className="secondary-button danger"
                      onClick={() => void deleteProject(project)}
                    >
                      Delete
                    </button>
                  </div>
                  <div className="project-meta">
                    <span className="project-workflow-lane">{projectWorkflowLaneLabel(project.workflow_lane)}</span>
                    <i />
                    <span>{phaseLabel(story, snapshot)}</span>
                    <i />
                    <span>{formatRuntime(snapshot?.target_duration_sec ?? story?.target_duration_sec ?? 300)} target</span>
                    <i />
                    <span>16:9</span>
                  </div>
                  <div className="project-readiness">
                    <span><b>{readiness}%</b> plan readiness</span>
                    <div
                      className="project-progress"
                      role="progressbar"
                      aria-valuenow={readiness}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${readiness}% plan readiness`}
                    >
                      <i style={{ width: `${readiness}%` }} />
                    </div>
                    <small>{openGates} gates open</small>
                  </div>
                  <dl className="project-counts">
                    <div><dt>Chapters</dt><dd>{chapters.length}</dd></div><div><dt>Scenes</dt><dd>{scenes.length}</dd></div>
                    <div><dt>Shots</dt><dd>{shots.length}</dd></div><div><dt>Characters</dt><dd>{characters.length}</dd></div>
                  </dl>
                </div>
                <footer>
                  <span className="project-team">
                    {characters.slice(0, 3).map((character) => <i key={character.id}>{projectInitials(character.name)}</i>)}
                    {characters.length > 3 ? <i>+{characters.length - 3}</i> : null}
                  </span>
                  <span>Created {formatUpdated(project.created_at)}</span>
                  <button type="button" onClick={open}>Open project →</button>
                </footer>
              </article>
            )
          })}
          <button type="button" className="new-project-card" onClick={onCreateNew}>
            <span>＋</span><b>Create a new project</b><small>Start from a story, blank structure, or imported package.</small>
          </button>
        </div>
      ) : null}
      {!loading && !error && !filtered.length ? (
        <EmptyState title={summaries.length ? 'No projects match.' : 'No projects yet.'} detail={summaries.length ? 'Clear the search or choose another status filter.' : 'Create a project to begin a production plan.'} />
      ) : null}
    </div>
  )
}

function NewProject({
  onBackToProjects,
  onOpenProject,
  initialWorkflowLane,
  initialPlanningAgent,
}: Pick<
  ProjectsProps,
  | 'onBackToProjects'
  | 'onOpenProject'
  | 'initialWorkflowLane'
  | 'initialPlanningAgent'
>) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<ProjectDraft>(() =>
    makeInitialDraft(initialWorkflowLane ?? null, initialPlanningAgent),
  )
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const idempotencyKey = useRef(`project-workspace-${crypto.randomUUID()}`)
  const minutes = Math.floor(draft.targetRuntime / 60)
  const seconds = draft.targetRuntime % 60

  const update = <Key extends keyof ProjectDraft>(key: Key, value: ProjectDraft[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  const selectWorkflowLane = (workflowLane: ProjectWorkflowLane) => {
    setDraft((current) => ({
      ...current,
      workflowLane,
      ...(workflowLane === 'agentless'
        ? {
            productionProfileKey: 'ltx_base@2',
            fps: 24,
            orchestrationMode: 'Manual',
            privacy: 'Local only',
          }
        : current.workflowLane === 'agentless'
          ? {
              productionProfileKey: EMPTY_DRAFT.productionProfileKey,
              fps: EMPTY_DRAFT.fps,
              orchestrationMode: EMPTY_DRAFT.orchestrationMode,
              privacy: EMPTY_DRAFT.privacy,
            }
          : {}),
    }))
    setError(null)
  }

  const setRuntime = (nextMinutes: number, nextSeconds: number) => {
    update('targetRuntime', Math.max(6, Math.min(3600, Math.max(0, nextMinutes) * 60 + Math.max(0, Math.min(59, nextSeconds)))))
  }

  const setChapterCount = (value: number) => {
    const nextCount = Math.max(1, Math.min(MAX_CHAPTER_COUNT, Math.round(value) || 1))
    setDraft((current) => {
      const nextIntake = [...current.chapterIntake]
      const targetDurationSec = Math.max(6, Math.round(current.targetRuntime / nextCount))
      const previousDefaultDuration = Math.max(6, Math.round(current.targetRuntime / current.requestedChapterCount))
      const untouchedChapterDefaults = nextIntake.slice(0, current.requestedChapterCount).every((chapter, index) => (
        chapter.title === `Chapter ${index + 1}` &&
        !chapter.summary.trim() &&
        !chapter.sourcePrompt.trim() &&
        !chapter.narrativePurpose.trim() &&
        !chapter.dramaticProgression.trim() &&
        !chapter.productionNotes.trim() &&
        chapter.targetDurationSec === previousDefaultDuration
      ))
      for (let index = nextIntake.length; index < nextCount; index += 1) {
        nextIntake.push(makeChapterIntakeDraft(index, targetDurationSec))
      }
      if (untouchedChapterDefaults) {
        for (let index = 0; index < nextCount; index += 1) {
          nextIntake[index] = {
            ...(nextIntake[index] ?? makeChapterIntakeDraft(index, targetDurationSec)),
            title: `Chapter ${index + 1}`,
            targetDurationSec,
          }
        }
      }
      return {
        ...current,
        requestedChapterCount: nextCount,
        chapterIntake: nextIntake,
      }
    })
  }

  const updateChapterIntake = <Key extends keyof ChapterIntakeDraft>(
    index: number,
    key: Key,
    value: ChapterIntakeDraft[Key],
  ) => {
    setDraft((current) => {
      const chapterIntake = [...current.chapterIntake]
      const fallbackDuration = Math.max(6, Math.round(current.targetRuntime / current.requestedChapterCount))
      const currentChapter = chapterIntake[index] ?? makeChapterIntakeDraft(index, fallbackDuration)
      chapterIntake[index] = { ...currentChapter, [key]: value }
      return { ...current, chapterIntake }
    })
  }

  const validate = () => {
    if (!draft.workflowLane) {
      setError('Choose CineForge Studio Workflow or Agentless Workflow.')
      return false
    }
    if (!draft.planningAgent) {
      setError('Choose a local planning agent.')
      return false
    }
    if (draft.themeId === 'biblical') {
      const context = biblicalContextPayload(draft.themeContext)
      if (!context) {
        setError('Complete every required Biblical context field before continuing.')
        return false
      }
      if (context.canon_context === 'hebrew_bible' && context.roman_presence !== 'none') {
        setError('Hebrew Bible contexts cannot include Roman presence.')
        return false
      }
      if (context.historical_preset.startsWith('hb_') && context.canon_context !== 'hebrew_bible') {
        setError('Choose Hebrew Bible for an HB historical preset.')
        return false
      }
      if (context.historical_preset.startsWith('nt_') && context.canon_context !== 'new_testament') {
        setError('Choose New Testament for an NT historical preset.')
        return false
      }
    }
    if (step === 2 && draft.sourceMode !== 'blank' && !draft.baseStory.trim()) {
      setError(draft.sourceMode === 'import' ? 'Choose a source file or paste its contents.' : 'Add the source story, script, or treatment.')
      return false
    }
    setError(null)
    return true
  }

  const loadSource = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      update('baseStory', await file.text())
      if (!draft.name.trim()) update('name', file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' '))
      setError(null)
    } catch {
      setError('That file could not be read. Try TXT, MD, or JSON.')
    }
  }

  const createProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!validate()) return
    const workflowLane = draft.workflowLane
    if (!workflowLane) return
    setSaving(true)
    setError(null)
    try {
      const dimensions = OUTPUT_DIMENSIONS[draft.aspectRatio] ?? OUTPUT_DIMENSIONS['16:9']
      const isAgentlessWorkflow = workflowLane === 'agentless'
      const hostedAllowed =
        !isAgentlessWorkflow && draft.privacy === 'Hosted providers allowed'
      const shouldRunInitialPlan = draft.sourceMode !== 'blank'
      const autoTitle = !draft.name.trim()
      const workingTitle = draft.name.trim() || 'CineForge Production'
      const chapterIntake = draft.chapterIntake.slice(0, draft.requestedChapterCount).map((chapter, index) => ({
        order_index: index,
        title: chapter.title.trim() || `Chapter ${index + 1}`,
        summary: chapter.summary.trim() || null,
        source_prompt: chapter.sourcePrompt.trim() || null,
        target_duration_sec: chapter.targetDurationSec,
        narrative_purpose: chapter.narrativePurpose.trim() || null,
        dramatic_progression: chapter.dramaticProgression.trim() || null,
        production_notes: chapter.productionNotes.trim() || null,
      }))
      const workspace = await api.createProjectWorkspace({
        idempotency_key: idempotencyKey.current,
        workflow_lane: workflowLane,
        theme_id: draft.themeId,
        theme_context: draft.themeId === 'biblical'
          ? biblicalContextPayload(draft.themeContext)
          : null,
        planning_agent: draft.planningAgent,
        planning_model_id: draft.planningModelId,
        prompt_artifact_format: 'json',
        prompt_schema_version: 'sineforge.local-planning-prompt/v1',
        name: workingTitle,
        auto_title: autoTitle,
        description: draft.description.trim() || null,
        source_mode: draft.sourceMode,
        story_title: workingTitle,
        base_story: draft.baseStory.trim(),
        target_duration_sec: draft.targetRuntime,
        audience: draft.audience.trim() || null,
        genre: draft.genre.trim() || null,
        tone: draft.tone.trim() || null,
        point_of_view: draft.pointOfView,
        visual_style: draft.visualStyle.trim() || null,
        production_notes: draft.productionNotes.trim() || null,
        language: draft.language,
        narration_dialogue_preference: draft.narrationDialoguePreference.trim() || null,
        source_fidelity_constraints: draft.sourceFidelityConstraints.trim() || null,
        content_constraints: draft.contentConstraints.trim() || null,
        requested_chapter_count: draft.requestedChapterCount,
        chapter_intake: chapterIntake,
        run_phase_one: shouldRunInitialPlan,
        bootstrap_phase_plan: shouldRunInitialPlan,
        auto_approve_phases_through: shouldRunInitialPlan ? 1 : null,
        run_phases_two_through_five: shouldRunInitialPlan,
        aspect_ratio: draft.aspectRatio,
        preview_width: dimensions.preview[0],
        preview_height: dimensions.preview[1],
        final_width: dimensions.final[0],
        final_height: dimensions.final[1],
        fps: isAgentlessWorkflow ? 24 : draft.fps,
        captions_enabled: true,
        audio_enabled: true,
        production_profile_key: isAgentlessWorkflow
          ? 'ltx_base@2'
          : draft.productionProfileKey,
        stitch_stage: draft.stitchStage,
        speaking_rate: 1,
        prefer_hosted_providers: hostedAllowed,
        prefer_local_providers: isAgentlessWorkflow
          ? true
          : draft.privacy !== 'Hosted providers allowed' ||
            draft.orchestrationMode === 'Hybrid',
        allow_model_download: !isAgentlessWorkflow,
        allow_rendering: !isAgentlessWorkflow,
        require_production_plan_approval: !shouldRunInitialPlan,
        orchestration_mode: isAgentlessWorkflow
          ? 'deterministic_python'
          : draft.orchestrationMode,
        privacy_preference: isAgentlessWorkflow ? 'Local only' : draft.privacy,
        quality_preference: draft.qualityPreference,
        cost_sensitivity: draft.costSensitivity,
      })
      onOpenProject?.(workspace.project.id, workspace.project.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create the project.')
    } finally {
      setSaving(false)
    }
  }

  const visibleChapterIntake = Array.from(
    { length: draft.requestedChapterCount },
    (_, index) => draft.chapterIntake[index] ?? makeChapterIntakeDraft(index, Math.max(6, Math.round(draft.targetRuntime / draft.requestedChapterCount))),
  )
  const chapterDurationTotal = visibleChapterIntake.reduce((total, chapter) => total + chapter.targetDurationSec, 0)
  const chapterRuntimeDelta = chapterDurationTotal - draft.targetRuntime
  const isAgentless = draft.workflowLane === 'agentless'
  const selectedPlanningAgent = localPlanningAgent(draft.planningAgent)
  const submitLabel = saving
    ? isAgentless
      ? `${selectedPlanningAgent?.label ?? 'Local agent'} · planning Phases 1–5…`
      : 'Local planning · completing Phases 1–5…'
    : isAgentless
      ? `Create with ${selectedPlanningAgent?.label ?? 'local agent'}`
      : draft.sourceMode === 'blank'
        ? '✦ Create project shell'
        : '✦ Create project & complete Phases 1–5'

  return (
    <form className="page new-project-page" onSubmit={createProject}>
      <div className="page-heading-row projects-heading">
        <PageHeader eyebrow="NEW PRODUCTION" title="Create a project" description="Set the creative foundation once. Every storyboard, reference, route, workflow, and export will inherit it." />
        <button type="button" className="secondary-button" onClick={onBackToProjects}>Cancel</button>
      </div>

      <div className="wizard-steps" aria-label="Project setup progress">
        {[{ n: 1, label: 'Project foundation' }, { n: 2, label: 'Story & timing' }, { n: 3, label: 'Production defaults' }].map((item) => (
          <button type="button" key={item.n} className={step === item.n ? 'active' : step > item.n ? 'complete' : ''} onClick={() => item.n < step && setStep(item.n)}>
            <span>{step > item.n ? '✓' : item.n}</span><b>{item.label}</b><i />
          </button>
        ))}
      </div>

      <div className="new-project-layout">
        <section className="wizard-panel">
          {step === 1 ? (
            <div className="wizard-section">
              <div className="wizard-heading"><span>STEP 1 OF 3</span><h2>Choose the workflow and project foundation</h2><p>Select how CineForge should operate, then choose the intake path. A title is optional.</p></div>
              <fieldset className="workflow-lane-fieldset">
                <legend>
                  Project workflow <em>Required</em>
                </legend>
                <div className="workflow-lane-options">
                  {PROJECT_WORKFLOW_LANES.map((option) => (
                    <label className="workflow-lane-card" key={option.value}>
                      <input
                        type="radio"
                        name="project-workflow-lane"
                        value={option.value}
                        checked={draft.workflowLane === option.value}
                        required
                        onChange={() => selectWorkflowLane(option.value)}
                      />
                      <span>
                        <b>{option.label}</b>
                        <small>{option.description}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <ThemeSelector
                value={draft.themeId}
                context={draft.themeContext}
                onChange={(themeId) => {
                  update('themeId', themeId)
                  setError(null)
                }}
                onContextChange={(key, value) => {
                  setDraft((current) => ({
                    ...current,
                    themeContext: { ...current.themeContext, [key]: value },
                  }))
                  setError(null)
                }}
              />
              {draft.workflowLane ? (
                <LocalPlanningAgentFieldset
                  name="wizard-planning-agent"
                  value={draft.planningAgent}
                  onChange={(planningAgent) => update('planningAgent', planningAgent)}
                  modelId={draft.planningModelId}
                  onModelChange={(planningModelId, planningAgent) => {
                    setDraft((current) => ({
                      ...current,
                      planningAgent,
                      planningModelId,
                    }))
                  }}
                  policyNote={
                    draft.workflowLane === 'agentless'
                      ? 'No hosted/API agents. The selected local LM Studio agent builds Phase 1; deterministic Python owns JSON scene manifests and rendering.'
                      : 'Live LM Studio catalog. Select any installed local model; the list refreshes automatically.'
                  }
                />
              ) : null}
              <div className="source-options">
                {SOURCE_OPTIONS.map((option) => (
                  <button type="button" key={option.id} className={draft.sourceMode === option.id ? 'selected' : ''} onClick={() => update('sourceMode', option.id)}>
                    <span>{option.icon}</span><b>{option.title}</b><small>{option.detail}</small>{draft.sourceMode === option.id ? <i>✓</i> : null}
                  </button>
                ))}
              </div>
              <div className="wizard-form">
                <label>Project name <em>Optional</em><input autoFocus value={draft.name} onChange={(event) => update('name', event.target.value)} placeholder="Leave blank and CineForge will create the title" /></label>
                <label>Short description<textarea value={draft.description} onChange={(event) => update('description', event.target.value)} placeholder="What are you creating, and what should the audience experience?" /></label>
              </div>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="wizard-section">
              <div className="wizard-heading">
                <span>STEP 2 OF 3</span>
                <h2>Give CineForge one creative prompt</h2>
                <p>
                  {draft.workflowLane === 'agentless'
                    ? `${selectedPlanningAgent?.label ?? 'The selected local agent'} will build the editable Phase 1 package locally. Hosted/API agents remain blocked, and deterministic Python retains control of JSON scene manifests and rendering.`
                    : 'Phase 1 will expand it into a complete editable script, narration/dialogue structure, pacing plan, duration analysis, assumptions, and QA report. Scene and shot segmentation remains locked for Phase 2.'}
                </p>
              </div>
              {draft.sourceMode === 'import' ? <label className="import-drop"><input type="file" accept=".txt,.md,.json,text/plain,application/json" onChange={(event) => void loadSource(event)} /><span>⇧</span><b>{draft.baseStory ? 'Source file loaded' : 'Choose a source file'}</b><small>TXT, Markdown, or JSON · the file stays in this browser until project creation</small></label> : null}
              {draft.sourceMode === 'blank' ? (
                <div className="blank-start-note"><span>✦</span><span><b>Blank structure selected</b><p>The new project will open as an empty project shell so you can build without inherited story content.</p></span></div>
              ) : (
                <div className="wizard-form"><label>{draft.sourceMode === 'import' ? 'Imported creative source' : 'Original creative prompt, story, or source text'} <em>Required</em><textarea className="source-story" value={draft.baseStory} onChange={(event) => update('baseStory', event.target.value)} placeholder="Describe the complete story, required moments, and creative boundaries in one prompt…" /><small>{draft.baseStory.trim().split(/\s+/).filter(Boolean).length.toLocaleString()} words</small></label></div>
              )}
              <div className="runtime-fields">
                <label>Target minutes<input type="number" min="0" max="60" value={minutes} onChange={(event) => setRuntime(Number(event.target.value), seconds)} /></label>
                <label>Seconds<input type="number" min="0" max="59" value={seconds} onChange={(event) => setRuntime(minutes, Number(event.target.value))} /></label>
                <div><span>Target runtime</span><b>{formatRuntime(draft.targetRuntime)}</b><small>Storyboard duration must reconcile exactly before approval.</small></div>
              </div>
              <div className="chapter-plan-panel">
                <header className="chapter-plan-head">
                  <div>
                    <span className="eyebrow">CHAPTER INTAKE</span>
                    <h3>Plan chapters before Phase 1</h3>
                    <p>Each chapter uses the same three-part intake pattern: foundation, story and timing, then production defaults.</p>
                  </div>
                  <label className="chapter-count-control">
                    <span>Chapters</span>
                    <input
                      aria-label="Number of chapters"
                      type="number"
                      min="1"
                      max={MAX_CHAPTER_COUNT}
                      value={draft.requestedChapterCount}
                      onChange={(event) => setChapterCount(Number(event.target.value))}
                    />
                  </label>
                </header>
                <div className="chapter-plan-summary">
                  <div>
                    <span>Chapter targets</span>
                    <b>{formatRuntime(chapterDurationTotal)}</b>
                  </div>
                  <small>
                    {chapterRuntimeDelta === 0
                      ? 'Chapter timing matches the project runtime.'
                      : `${chapterRuntimeDelta > 0 ? '+' : '-'}${formatRuntime(Math.abs(chapterRuntimeDelta))} from the project target.`}
                  </small>
                </div>
                <div className="chapter-plan-list">
                  {visibleChapterIntake.map((chapter, index) => (
                    <details key={index} open={index < 3}>
                      <summary>
                        <span>{chapterCode(index)}</span>
                        <b>{chapter.title.trim() || `Chapter ${index + 1}`}</b>
                        <small>{formatRuntime(chapter.targetDurationSec)}</small>
                      </summary>
                      <ChapterIntakeForm
                        draft={chapter}
                        index={index}
                        onChange={(key, value) => updateChapterIntake(index, key, value)}
                      />
                    </details>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="wizard-section">
              <div className="wizard-heading"><span>STEP 3 OF 3</span><h2>Choose production defaults</h2><p>These settings guide planning recommendations. Nothing will render or download during project creation.</p></div>
              <div className="wizard-defaults wizard-form">
                <label>Audience<input value={draft.audience} onChange={(event) => update('audience', event.target.value)} /></label>
                <label>Language<input value={draft.language} onChange={(event) => update('language', event.target.value)} /></label>
                <label>Genre<input value={draft.genre} onChange={(event) => update('genre', event.target.value)} /></label>
                <label>Tone<input value={draft.tone} onChange={(event) => update('tone', event.target.value)} /></label>
                <label>Point of view<select value={draft.pointOfView} onChange={(event) => update('pointOfView', event.target.value)}><option>Third person</option><option>First person</option><option>Second person</option><option>Omniscient</option></select></label>
                <label className="full-span">Visual style<input value={draft.visualStyle} onChange={(event) => update('visualStyle', event.target.value)} /></label>
                <label>Aspect ratio<select value={draft.aspectRatio} onChange={(event) => update('aspectRatio', event.target.value)}><option>16:9</option><option>9:16</option><option>2.39:1</option><option>1:1</option></select></label>
                <label>Frame rate<select value={draft.fps} disabled={isAgentless} onChange={(event) => update('fps', Number(event.target.value))}><option value="24">24 fps</option><option value="30">30 fps</option><option value="60">60 fps</option></select></label>
                <label>
                  Base-model profile
                  <select
                    value={draft.productionProfileKey}
                    disabled={isAgentless}
                    onChange={(event) => update('productionProfileKey', event.target.value as ProjectDraft['productionProfileKey'])}
                  >
                    <option value="ltx_base@1">LTX Base v1 · qualified compatibility profile</option>
                    <option value="ltx_base@2">
                      {isAgentless
                        ? 'Agentless scene reset · FLUX.2 + LTX-2.3'
                        : 'LTX Base v2 · 8–15 second Sequence Sheet'}
                    </option>
                    <option value="wan_base@1" disabled>WAN Base v1 · on hold after failed dry run</option>
                  </select>
                  <small>
                    {draft.productionProfileKey === 'wan_base@1'
                      ? 'WAN remains visible for existing projects, but it is disabled and cannot queue work while its failed dry run is on hold.'
                      : isAgentless
                        ? 'Compiles fresh multi-reference FLUX anchors and LTX-2.3 Ingredients plus first-frame I2V jobs. Execution remains fail-closed until exact workflows are admitted.'
                        : draft.productionProfileKey === 'ltx_base@2'
                        ? 'Uses one visible LTX request per 8–15 second Sequence Sheet row. Rendering stays fail-closed until the exact API workflow passes local qualification.'
                        : 'Preserves the existing qualified 6–10 second LTX compatibility contract.'}
                  </small>
                </label>
                <label>
                  Picture stitch stage
                  <select
                    value={draft.stitchStage}
                    onChange={(event) => update('stitchStage', event.target.value as ProjectDraft['stitchStage'])}
                  >
                    <option value="phase7_before_audio">Phase 7 · stitch and lock before audio</option>
                    <option value="phase8_before_foley">Phase 8 · materialize locked EDL before Foley</option>
                  </select>
                </label>
                <label>Orchestration<select value={draft.orchestrationMode} disabled={isAgentless} onChange={(event) => update('orchestrationMode', event.target.value)}><option value="Hybrid">Hybrid</option><option value="Automatic">Automatic</option><option value="Manual">Deterministic Python + local agent planning</option></select></label>
                <label>Privacy preference<select value={draft.privacy} disabled={isAgentless} onChange={(event) => update('privacy', event.target.value)}><option>Prefer local for bulk work</option><option>Hosted providers allowed</option><option>Local only</option></select></label>
                <label>Quality preference<select value={draft.qualityPreference} onChange={(event) => update('qualityPreference', event.target.value)}><option>Quality weighted</option><option>Balanced</option><option>Speed weighted</option></select></label>
                <label>Cost sensitivity<select value={draft.costSensitivity} onChange={(event) => update('costSensitivity', event.target.value)}><option>Balanced</option><option>Minimize hosted usage</option><option>Quality first</option></select></label>
                <label className="full-span">Narration and dialogue preference<textarea value={draft.narrationDialoguePreference} onChange={(event) => update('narrationDialoguePreference', event.target.value)} /></label>
                <label className="full-span">Source-fidelity constraints<textarea value={draft.sourceFidelityConstraints} onChange={(event) => update('sourceFidelityConstraints', event.target.value)} placeholder="Required source events, facts, canon, quotation, or adaptation boundaries…" /></label>
                <label className="full-span">Content constraints<textarea value={draft.contentConstraints} onChange={(event) => update('contentConstraints', event.target.value)} placeholder="Forbidden actions, sensitive-content boundaries, or other non-negotiables…" /></label>
                <label className="full-span">Production notes<textarea value={draft.productionNotes} onChange={(event) => update('productionNotes', event.target.value)} placeholder="Continuity rules, visual boundaries, required moments, or technical constraints…" /></label>
              </div>
            </div>
          ) : null}

          {error ? <div className="wizard-error" role="alert">△ <span>{error}</span></div> : null}
          <footer className="wizard-actions">
            <button type="button" className="secondary-button" onClick={() => step === 1 ? onBackToProjects?.() : setStep((current) => current - 1)}>{step === 1 ? 'Cancel' : 'Back'}</button>
            <span>Step {step} of 3</span>
            {step < 3 ? <button type="button" className="primary-button" onClick={() => validate() && setStep((current) => current + 1)}>Continue →</button> : <button type="submit" className="primary-button" disabled={saving}>{submitLabel}</button>}
          </footer>
        </section>

        <aside className="project-preview">
          <div className="preview-cover"><span className="cover-grid" /><span className="cover-orb orb-a" /><span className="cover-orb orb-b" /><b>{projectInitials(draft.name || 'New project')}</b><small>PROJECT PREVIEW</small></div>
          <div className="preview-copy"><span className="eyebrow">PRODUCTION FOUNDATION</span><h2>{draft.name.trim() || 'Title generated from your prompt'}</h2><p>{draft.description.trim() || (isAgentless ? 'Your source and deterministic production settings remain editable.' : 'Your complete local planning package remains editable after creation.')}</p></div>
          <dl>
            <div><dt>Workflow</dt><dd>{draft.workflowLane ? projectWorkflowLaneLabel(draft.workflowLane) : 'Choose a workflow'}</dd></div>
            <div><dt>Theme</dt><dd>{creativeThemeLabel(draft.themeId)}</dd></div>
            <div><dt>Source</dt><dd>{SOURCE_OPTIONS.find((option) => option.id === draft.sourceMode)?.title.replace('Start from a ', '')}</dd></div>
            <div><dt>Target runtime</dt><dd>{formatRuntime(draft.targetRuntime)}</dd></div><div><dt>Output</dt><dd>{draft.aspectRatio} · {draft.fps} fps</dd></div>
            <div><dt>Chapters</dt><dd>{draft.requestedChapterCount}</dd></div>
            <div>
              <dt>Base model</dt>
              <dd>
                {isAgentless
                  ? 'Agentless scene reset · FLUX.2 + LTX-2.3'
                  : draft.productionProfileKey === 'wan_base@1'
                  ? 'WAN Base v1 · on hold'
                  : draft.productionProfileKey === 'ltx_base@2'
                    ? 'LTX Base v2 · 8–15 s'
                    : 'LTX Base v1'}
              </dd>
            </div>
            <div><dt>Planning agent</dt><dd>{selectedPlanningAgent?.label ?? 'Qwen3 4B Hivemind'}</dd></div>
            <div><dt>Mode</dt><dd>{isAgentless ? 'Local agent planning · deterministic production' : draft.orchestrationMode === 'Manual' ? 'Manual creative routing' : draft.orchestrationMode}</dd></div><div><dt>Visual style</dt><dd>{draft.visualStyle}</dd></div>
          </dl>
          <div className="creation-boundary">
            <span>▣</span>
            {isAgentless ? (
              <p><b>Local-only Agentless creation</b>The selected LM Studio agent builds Phases 1–5 using structured JSON prompts. Hosted/API agents stay blocked, and no rendering starts during creation.</p>
            ) : (
              <p><b>Local planning through Phase 5</b>One submission creates the script, scenes, shots, characters, assets, and production prompt package. Phases 6–8 stay locked. No image, voice, video, audio, ComfyUI, FFmpeg, model-download, or render job starts during creation.</p>
            )}
          </div>
        </aside>
      </div>
      {saving && draft.sourceMode !== 'blank' ? (
        <div className="phase-one-progress" role="status" aria-live="polite">
          <div className="phase-one-progress-card">
            <span className="phase-one-spinner" aria-hidden="true" />
            <div><span className="eyebrow">LOCAL PLANNING · PHASES 1–5 OF 8</span><h2>Building your production plan</h2><p>{selectedPlanningAgent?.label ?? 'The selected local agent'} is creating and validating the script, scene breakdown, shot list, character and asset bible, and production prompt package.</p></div>
            <ol>
              {[
                'Script and Narrative Development',
                'Scene and Shot Segmentation',
                'Character Development',
                'Location and Key-Asset Development',
                'Production Prompt and Workflow Package',
                'Image and Voice Generation and Mapping',
                'Video Generation, Continuity, Assembly, and Picture Lock',
                'Foley, Audio Mix, Final Mux, and Delivery QA',
              ].map((name, index) => (
                <li key={name} className={index < 5 ? 'active' : undefined}>
                  <b>{index + 1}</b>
                  <span>{name}<small>{index < 5 ? 'Local planning · validation in progress' : 'Locked · not started'}</small></span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      ) : null}
    </form>
  )
}

export function Projects({
  mode = 'list',
  onCreateNew,
  onBackToProjects,
  onOpenProject,
  onOpenProjectPage,
  onProjectsLoaded,
  onNavigateStudio,
  onContinueAgentless,
  initialWorkflowLane,
  initialPlanningAgent,
  currentProjectId,
}: ProjectsProps) {
  return mode === 'create'
    ? (
      <NewProject
        onBackToProjects={onBackToProjects}
        onOpenProject={onOpenProject}
        initialWorkflowLane={initialWorkflowLane}
        initialPlanningAgent={initialPlanningAgent}
      />
    )
    : (
      <ProjectList
        onCreateNew={onCreateNew}
        onOpenProject={onOpenProject}
        onOpenProjectPage={onOpenProjectPage}
        onProjectsLoaded={onProjectsLoaded}
        onNavigateStudio={onNavigateStudio}
        onContinueAgentless={onContinueAgentless}
        currentProjectId={currentProjectId}
      />
    )
}
