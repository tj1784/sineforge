import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  api,
  type Chapter,
  type ManualTaskRoute,
  type OrchestrationRoutingMode,
  type OrchestrationRun,
  type OrchestrationRunDetail,
  type PlanningTaskType,
  type ProposalDiff,
  type ProviderCatalogEntry,
  type ProviderProfile,
  type RoutingPreflightResponse,
  type Scene,
  type StoryboardProposal,
} from '../../api/client'
import { formatDate } from '../../components/formatDate'
import { useStudio } from '../StudioState'
import { formatDuration } from '../utils'
import { EmptyState, LoadingState } from '../components/StateBlocks'
import { ChapterIntakeForm } from '../../components/ChapterIntakeForm'
import { makeChapterIntakeDraft, type ChapterIntakeDraft } from '../../components/chapterIntake'
import { isPlanningAgent, type PlanningAgent } from '../../planningAgents'
import { formatPlanningRoute } from '../planningRouteDisplay'

type ProviderPreference = 'local' | 'hosted' | 'mixed'
type LogicalModel = NonNullable<ManualTaskRoute['logical_model']>

const PLANNING_TASKS: Array<{
  task: PlanningTaskType
  label: string
  logicalModel: LogicalModel
}> = [
  { task: 'story_structure', label: 'Story adaptation', logicalModel: 'sol' },
  { task: 'character_bible', label: 'Character profile', logicalModel: 'terra' },
  { task: 'scene_breakdown', label: 'Scene breakdown', logicalModel: 'terra' },
  { task: 'shot_list', label: 'Shot list', logicalModel: 'luna' },
  { task: 'prompt_package', label: 'Prompt packages', logicalModel: 'luna' },
  { task: 'production_proposal', label: 'Final proposal', logicalModel: 'sol' },
]

const BUILTIN_MOCK_ROUTE = 'builtin:mock'
const LOCAL_AGENT_LABELS: Record<string, string> = {
  qwen: 'Qwen3 4B Hivemind',
  sulphur: 'Sulphur 2 Base',
  grok: 'Grok',
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value
}

function statusClass(status: string | null | undefined): string {
  if (['completed', 'validated', 'applied', 'valid', 'succeeded'].includes(status ?? '')) return 'verified'
  if (['failed', 'canceled', 'rejected', 'invalid', 'superseded'].includes(status ?? '')) return 'blocked'
  return 'unknown'
}

function diffValue(value: unknown): string {
  if (value == null) return '—'
  const serialized = typeof value === 'string' ? value : JSON.stringify(value)
  return serialized.length > 180 ? `${serialized.slice(0, 177)}…` : serialized
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function stringValue(value: unknown, fallback = 'Not recorded'): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function proposalPayloadSummary(payload: Record<string, unknown>): {
  title: string
  targetDuration: string
  chapters: number
  scenes: number
  shots: number
  characters: number
  payloadSize: string
} {
  const story = objectValue(payload.story)
  const chapters = arrayValue(story.chapters)
  const scenes = chapters.flatMap((chapter) => arrayValue(objectValue(chapter).scenes))
  const shots = scenes.flatMap((scene) => arrayValue(objectValue(scene).shots))
  const characters = arrayValue(story.characters)
  const bytes = new Blob([JSON.stringify(payload)]).size

  return {
    title: stringValue(story.title),
    targetDuration:
      typeof story.target_duration_sec === 'number'
        ? formatDuration(story.target_duration_sec)
        : stringValue(story.target_duration_sec, 'Not recorded'),
    chapters: chapters.length,
    scenes: scenes.length,
    shots: shots.length,
    characters: characters.length,
    payloadSize: `${Math.max(1, Math.round(bytes / 1024)).toLocaleString()} KB`,
  }
}

function parseRuntimeInput(value: string | number, fallbackSec: number): number {
  const raw = String(value).trim()
  if (!raw) return fallbackSec

  if (raw.includes(':')) {
    const parts = raw.split(':').map((part) => Number(part.trim()))
    if (parts.some((part) => !Number.isFinite(part) || part < 0)) return fallbackSec
    if (parts.length === 2) {
      const [minutes, seconds] = parts
      if (seconds >= 60) return fallbackSec
      return Math.max(1, Math.round(minutes * 60 + seconds))
    }
    if (parts.length === 3) {
      const [hours, minutes, seconds] = parts
      if (minutes >= 60 || seconds >= 60) return fallbackSec
      return Math.max(1, Math.round(hours * 3600 + minutes * 60 + seconds))
    }
    return fallbackSec
  }

  const numeric = Number(raw)
  return Number.isFinite(numeric) && numeric > 0 ? Math.round(numeric) : fallbackSec
}

export function StoryPage() {
  const {
    data,
    addHierarchy,
    updateStoryFields,
    reload,
    setMessage,
    busy,
    workflowLane,
  } = useStudio()
  const storyId = data?.story.id ?? ''
  const projectId = data?.story.project_id ?? ''
  const isAgentless = workflowLane === 'agentless'
  const [title, setTitle] = useState(data?.story.title ?? '')
  const [logline, setLogline] = useState(data?.story.logline ?? '')
  const [synopsis, setSynopsis] = useState(data?.story.synopsis ?? '')
  const [baseStory, setBaseStory] = useState(data?.story.base_story ?? '')
  const [audience, setAudience] = useState(data?.story.audience ?? '')
  const [tone, setTone] = useState(data?.story.tone ?? '')
  const [genre, setGenre] = useState(data?.story.genre ?? '')
  const [visualStyle, setVisualStyle] = useState(data?.story.visual_style ?? '')
  const [pointOfView, setPointOfView] = useState(data?.story.point_of_view ?? '')
  const [productionNotes, setProductionNotes] = useState(data?.story.production_notes ?? '')
  const [targetRuntime, setTargetRuntime] = useState(formatDuration(data?.story.target_duration_sec ?? 300))
  const [chapterCreatorOpen, setChapterCreatorOpen] = useState(false)
  const [chapterDraft, setChapterDraft] = useState<ChapterIntakeDraft>(() => makeChapterIntakeDraft(0))
  const [chapterOrderSlot, setChapterOrderSlot] = useState(1)
  const [expanded, setExpanded] = useState<string[]>([])
  const planningDetailsRef = useRef<HTMLDetailsElement | null>(null)

  const [actorName, setActorName] = useState('')
  const [routingMode, setRoutingMode] = useState<OrchestrationRoutingMode>('automatic')
  const [providerPreference, setProviderPreference] = useState<ProviderPreference>('local')
  const [planningAgent, setPlanningAgent] = useState<PlanningAgent>('qwen')
  const [providerProfiles, setProviderProfiles] = useState<ProviderProfile[]>([])
  const [providerCatalog, setProviderCatalog] = useState<ProviderCatalogEntry[]>([])
  const [routingPreflight, setRoutingPreflight] = useState<RoutingPreflightResponse | null>(null)
  const [manualRouteSelections, setManualRouteSelections] = useState<
    Partial<Record<PlanningTaskType, string>>
  >({})
  const [maxSteps, setMaxSteps] = useState(PLANNING_TASKS.length)
  const [repairBudget, setRepairBudget] = useState(3)
  const [timeBudgetSec, setTimeBudgetSec] = useState(300)
  const [transportRetryLimit, setTransportRetryLimit] = useState(2)
  const [runs, setRuns] = useState<OrchestrationRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [selectedRun, setSelectedRun] = useState<OrchestrationRunDetail | null>(null)
  const [proposals, setProposals] = useState<StoryboardProposal[]>([])
  const [selectedProposalId, setSelectedProposalId] = useState('')
  const [selectedProposal, setSelectedProposal] = useState<StoryboardProposal | null>(null)
  const [proposalDiff, setProposalDiff] = useState<ProposalDiff | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [bypassPlanningGates, setBypassPlanningGates] = useState(true)
  const [planningLoading, setPlanningLoading] = useState(true)
  const [planningBusy, setPlanningBusy] = useState(false)
  const [planningError, setPlanningError] = useState<string | null>(null)
  const [planningNotice, setPlanningNotice] = useState<string | null>(null)
  const [structureBusy, setStructureBusy] = useState(false)
  const [structureError, setStructureError] = useState<string | null>(null)
  const syncedStoryId = data?.story.id ?? ''
  const syncedStoryVersionId = data?.story.active_storyboard_version_id ?? ''
  const syncedTitle = data?.story.title ?? ''
  const syncedLogline = data?.story.logline ?? ''
  const syncedSynopsis = data?.story.synopsis ?? ''
  const syncedBaseStory = data?.story.base_story ?? ''

  useEffect(() => {
    if (!syncedStoryId) return
    const timer = window.setTimeout(() => {
      setTitle(syncedTitle)
      setLogline(syncedLogline)
      setSynopsis(syncedSynopsis)
      setBaseStory(syncedBaseStory)
      setAudience(data?.story.audience ?? '')
      setTone(data?.story.tone ?? '')
      setGenre(data?.story.genre ?? '')
      setVisualStyle(data?.story.visual_style ?? '')
      setPointOfView(data?.story.point_of_view ?? '')
      setProductionNotes(data?.story.production_notes ?? '')
      setTargetRuntime(formatDuration(data?.story.target_duration_sec ?? 300))
      const ids = (data?.chapters ?? []).map((c) => c.id)
      setExpanded((prev) => (prev.length ? prev.filter((id) => ids.includes(id)) : ids))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [
    syncedStoryId,
    syncedStoryVersionId,
    syncedTitle,
    syncedLogline,
    syncedSynopsis,
    syncedBaseStory,
    data?.story.audience,
    data?.story.tone,
    data?.story.genre,
    data?.story.visual_style,
    data?.story.point_of_view,
    data?.story.production_notes,
    data?.story.target_duration_sec,
    data?.chapters,
  ])

  const loadPlanning = useCallback(
    async (preferredRunId?: string, preferredProposalId?: string, silent = false) => {
      if (!storyId) return
      if (!silent) {
        setPlanningLoading(true)
        setPlanningError(null)
      }
      try {
        const [runList, proposalList, profileList, catalog, projectSettings] = await Promise.all([
          api.listOrchestrationRuns(storyId),
          api.listStoryProposals(storyId),
          api.listProviderProfiles().catch(() => []),
          api.listPlanningProviders().catch(() => null),
          projectId ? api.getSettings(projectId).catch(() => null) : null,
        ])
        setRuns(runList)
        setProposals(proposalList)
        setProviderProfiles(profileList)
        setProviderCatalog(catalog?.providers ?? [])
        const projectPlanningAgent = projectSettings?.prompting_policy_json.planning_agent
        setPlanningAgent(isPlanningAgent(projectPlanningAgent) ? projectPlanningAgent : 'qwen')

        const runId =
          (preferredRunId && runList.some((run) => run.id === preferredRunId) && preferredRunId) ||
          runList.at(0)?.id ||
          ''
        setSelectedRunId(runId)
        setSelectedRun(runId ? await api.getOrchestrationRun(runId) : null)

        const proposalId =
          (preferredProposalId &&
            proposalList.some((proposal) => proposal.id === preferredProposalId) &&
            preferredProposalId) ||
          proposalList.at(0)?.id ||
          ''
        setSelectedProposalId(proposalId)
        if (proposalId) {
          const proposal = await api.getProposal(proposalId)
          setSelectedProposal(proposal)
          try {
            setProposalDiff(await api.getProposalDiff(proposalId))
          } catch (error) {
            setProposalDiff(null)
            setPlanningError(
              `Proposal loaded, but its diff is unavailable: ${errorMessage(error, 'Unknown diff error.')}`,
            )
          }
        } else {
          setSelectedProposal(null)
          setProposalDiff(null)
        }
      } catch (error) {
        setPlanningError(errorMessage(error, 'Could not load orchestration runs and proposals.'))
      } finally {
        if (!silent) setPlanningLoading(false)
      }
    },
    [projectId, storyId],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPlanning(), 0)
    return () => window.clearTimeout(timer)
  }, [loadPlanning])

  useEffect(() => {
    if (!selectedRunId || !['pending', 'running'].includes(selectedRun?.status ?? '')) return

    let canceled = false
    let timer = 0
    const poll = async () => {
      await loadPlanning(selectedRunId, selectedProposalId || undefined, true)
      if (!canceled) timer = window.setTimeout(() => void poll(), 1250)
    }
    timer = window.setTimeout(() => void poll(), 500)
    return () => {
      canceled = true
      window.clearTimeout(timer)
    }
  }, [loadPlanning, selectedProposalId, selectedRun?.status, selectedRunId])

  if (!data) return null

  const story = data.story
  const chapters = data.chapters
  const providerFactById = new Map(providerCatalog.map((provider) => [provider.provider_identifier, provider]))
  const studioRouteOptions = [
      {
        value: BUILTIN_MOCK_ROUTE,
        label: 'Built-in mock · local · available',
        providerIdentifier: 'mock',
        availabilityStatus: providerFactById.get('mock')?.availability_status ?? 'available',
        privacy: providerFactById.get('mock')?.privacy_classification ?? 'local',
      },
      ...providerProfiles.map((profile) => {
      const fact = providerFactById.get(profile.provider_identifier)
      return {
        value: profile.id,
        label: `${profile.display_name} · ${fact?.availability_status ?? 'unknown'} · ${fact?.privacy_classification ?? profile.privacy_classification ?? 'unknown'}`,
        providerIdentifier: profile.provider_identifier,
        availabilityStatus: fact?.availability_status ?? 'unknown',
        privacy: fact?.privacy_classification ?? profile.privacy_classification ?? 'unknown',
      }
    }),
  ]
  const routeOptions = isAgentless
    ? studioRouteOptions.filter(
        (option) => option.providerIdentifier === planningAgent,
      )
    : studioRouteOptions
  const visibleProviderFacts = isAgentless
    ? providerCatalog.filter(
        (provider) => provider.provider_identifier === planningAgent,
      )
    : providerCatalog

  const disabled = busy || planningBusy || planningLoading
  const structureDisabled = busy || structureBusy
  const actor = actorName.trim() || 'Robert'
  const runCanStart = selectedRun?.status === 'pending'
  const runCanCancel = selectedRun?.status === 'pending' || selectedRun?.status === 'running'
  const runCanIterate = Boolean(
    selectedRun && !['pending', 'running'].includes(selectedRun.status),
  )
  const proposalIsTerminal = ['applied', 'rejected', 'superseded'].includes(selectedProposal?.status ?? '')
  const proposalHasValidationErrors =
    selectedProposal?.validation_status === 'invalid' ||
    Boolean(selectedProposal?.validation_errors.length)
  const proposalCanReview =
    Boolean(selectedProposal) &&
    !proposalIsTerminal &&
    !proposalHasValidationErrors
  const proposalCanApply =
    Boolean(selectedProposal) &&
    !proposalIsTerminal &&
    !proposalHasValidationErrors &&
    (bypassPlanningGates ||
      (selectedProposal?.status === 'validated' &&
        proposalDiff?.proposal_id === selectedProposal?.id))

  async function chooseRun(runId: string) {
    setSelectedRunId(runId)
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      setSelectedRun(runId ? await api.getOrchestrationRun(runId) : null)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not load the selected run.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function chooseProposal(proposalId: string) {
    setSelectedProposalId(proposalId)
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      if (!proposalId) {
        setSelectedProposal(null)
        setProposalDiff(null)
        return
      }
      const proposal = await api.getProposal(proposalId)
      setSelectedProposal(proposal)
      try {
        setProposalDiff(await api.getProposalDiff(proposalId))
      } catch (error) {
        setProposalDiff(null)
        setPlanningError(
          `Proposal loaded, but its diff is unavailable: ${errorMessage(error, 'Unknown diff error.')}`,
        )
      }
    } catch (error) {
      setProposalDiff(null)
      setPlanningError(errorMessage(error, 'Could not inspect the selected proposal.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  function buildManualRoutes(): ManualTaskRoute[] {
    if (isAgentless) return []
    return PLANNING_TASKS.flatMap<ManualTaskRoute>(({ task, logicalModel }) => {
        const selection = manualRouteSelections[task]
        if (!selection) return []
        if (selection === BUILTIN_MOCK_ROUTE) {
          return [{
            task_type: task,
            provider_identifier: 'mock',
            logical_model: logicalModel,
            rationale: 'Explicit Studio route to the deterministic local mock provider.',
          }]
        }
        const profile = providerProfiles.find((item) => item.id === selection)
        if (!profile) return []
        return [{
          task_type: task,
          provider_identifier: profile.provider_identifier,
          logical_model: logicalModel,
          resolved_model: profile.provider_model_id,
          rationale: `Explicit Studio route through provider profile ${profile.display_name}.`,
        }]
      })
  }

  function changeRoutingMode(nextMode: OrchestrationRoutingMode) {
    if (isAgentless) {
      setRoutingMode('automatic')
      return
    }
    setRoutingMode(nextMode)
    if (nextMode === 'manual') {
      setManualRouteSelections((current) => {
        const next = { ...current }
        for (const { task } of PLANNING_TASKS) next[task] = next[task] || BUILTIN_MOCK_ROUTE
        return next
      })
    }
  }

  async function createRun() {
    setPlanningBusy(true)
    setPlanningError(null)
    setPlanningNotice(null)
    try {
      const effectiveRoutingMode: OrchestrationRoutingMode = isAgentless
        ? 'automatic'
        : routingMode
      const manualRoutes = buildManualRoutes()
      if (effectiveRoutingMode === 'manual' && manualRoutes.length !== PLANNING_TASKS.length) {
        throw new Error('Manual routing requires an explicit provider route for every planning task.')
      }
      const preflight = await api.validateStoryRouting(story.id, {
        routing_mode: effectiveRoutingMode,
        manual_routes: manualRoutes,
        prefer_local_providers: isAgentless || providerPreference !== 'hosted',
        prefer_hosted_providers: !isAgentless && providerPreference !== 'local',
        max_steps: maxSteps,
        time_budget_sec: timeBudgetSec,
        transport_retry_limit: transportRetryLimit,
        task_types: PLANNING_TASKS.map((item) => item.task),
      })
      setRoutingPreflight(preflight)
      if (!preflight.valid) {
        const details = preflight.errors.map((issue) => issue.message).join(' ')
        throw new Error(details || 'Routing preflight rejected this run configuration.')
      }
      const result = await api.createOrchestrationRun({
        story_id: story.id,
        base_storyboard_version_id:
          story.approval_state === 'approved' ? story.active_storyboard_version_id ?? null : null,
        requested_by: actor || null,
        routing_mode: effectiveRoutingMode,
        manual_routes: manualRoutes,
        prefer_local_providers: isAgentless || providerPreference !== 'hosted',
        prefer_hosted_providers: !isAgentless && providerPreference !== 'local',
        max_steps: maxSteps,
        repair_budget: repairBudget,
        time_budget_sec: timeBudgetSec,
        transport_retry_limit: transportRetryLimit,
        task_types: PLANNING_TASKS.map((item) => item.task),
        idempotency_key: `studio-${crypto.randomUUID()}`,
      })
      if (bypassPlanningGates) {
        const started = await api.startOrchestrationRun(result.run.id)
        setPlanningNotice(
          result.idempotent_replay
            ? started.message
            : 'Planning draft generation started. Phases 1–5 will populate for inspection when the run completes.',
        )
        await loadPlanning(started.run.id, selectedProposalId || undefined, true)
        return
      }
      setPlanningNotice(
        result.idempotent_replay
          ? 'The existing idempotent pending run was loaded. It has not been started.'
          : 'Planning run created in pending state. Start it explicitly when ready.',
      )
      await loadPlanning(result.run.id, selectedProposalId || undefined)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not create the planning run.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function startRun() {
    if (!selectedRun || !runCanStart) return
    setPlanningBusy(true)
    setPlanningError(null)
    setPlanningNotice('The planning request is running. No proposal will be applied automatically.')
    try {
      const result = await api.startOrchestrationRun(selectedRun.id)
      setPlanningNotice(result.message)
      setRuns((current) => current.map((run) => (run.id === result.run.id ? result.run : run)))
      setSelectedRun((current) =>
        current?.id === result.run.id ? { ...current, ...result.run } : current,
      )
      void loadPlanning(result.run.id, selectedProposalId || undefined, true)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not start the selected run.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function retryRun() {
    if (!selectedRun || !runCanIterate) return
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      const result = await api.retryOrchestrationRun(selectedRun.id, actor || undefined)
      if (bypassPlanningGates) {
        const started = await api.startOrchestrationRun(result.run.id)
        setPlanningNotice(
          result.idempotent_replay
            ? started.message
            : 'New planning iteration started. It will not overwrite the previous draft.',
        )
        await loadPlanning(started.run.id, selectedProposalId || undefined, true)
        return
      }
      setPlanningNotice(
        result.idempotent_replay
          ? 'The existing pending retry was loaded. Start it explicitly when ready.'
          : 'A new bounded retry run was created in pending state. Prior run history was preserved.',
      )
      await loadPlanning(result.run.id, selectedProposalId || undefined)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not create a retry for the selected run.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function cancelRun() {
    if (!selectedRun || !runCanCancel) return
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      const result = await api.cancelOrchestrationRun(
        selectedRun.id,
        'Canceled from Story & chapters planning review.',
        actor || undefined,
      )
      setPlanningNotice(result.message)
      await loadPlanning(result.run.id, selectedProposalId || undefined)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not cancel the selected run.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function reviewProposal() {
    if (!selectedProposal || !proposalCanReview) return
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      const proposal = await api.reviewProposal(selectedProposal.id, actor, reviewNotes)
      setPlanningNotice('Review note saved. You can apply, edit manually, reject, or generate another iteration.')
      await loadPlanning(selectedRunId || undefined, proposal.id)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not review the proposal.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function rejectProposal() {
    if (!selectedProposal || !rejectionReason.trim() || proposalIsTerminal) return
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      const proposal = await api.rejectProposal(selectedProposal.id, actor, rejectionReason.trim())
      setPlanningNotice('Proposal rejected. No storyboard changes were applied.')
      await loadPlanning(selectedRunId || undefined, proposal.id)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not reject the proposal.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function applyProposal() {
    if (!selectedProposal || !proposalCanApply) return
    setPlanningBusy(true)
    setPlanningError(null)
    try {
      const result = await api.applyProposal(
        selectedProposal.id,
        actor,
        proposalDiff?.base_storyboard_version_id ?? selectedProposal.base_storyboard_version_id,
        proposalDiff?.base_content_hash ?? null,
      )
      await reload(story.id)
      await loadPlanning(selectedRunId || undefined, selectedProposal.id)
      const notice = `Proposal applied as storyboard version ${result.version_number}. The live plan was refreshed.`
      setPlanningNotice(notice)
      setMessage(notice)
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not apply the proposal.'))
    } finally {
      setPlanningBusy(false)
    }
  }

  async function copyProposalPayload() {
    if (!selectedProposal) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(selectedProposal.payload, null, 2))
      setPlanningNotice('Proposal JSON copied to clipboard.')
    } catch (error) {
      setPlanningError(errorMessage(error, 'Could not copy proposal JSON.'))
    }
  }

  function downloadProposalPayload() {
    if (!selectedProposal) return
    const json = JSON.stringify(selectedProposal.payload, null, 2)
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `sineforge-proposal-${shortId(selectedProposal.id)}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setPlanningNotice('Proposal JSON download started.')
  }

  async function persistStructure(action: () => Promise<unknown>, successMessage: string): Promise<boolean> {
    setStructureBusy(true)
    setStructureError(null)
    try {
      await action()
      await reload(story.id)
      setMessage(successMessage)
      return true
    } catch (error) {
      const text = errorMessage(error, 'Could not update the persisted story structure.')
      setStructureError(text)
      setMessage(text)
      return false
    } finally {
      setStructureBusy(false)
    }
  }

  function newChapterDuration() {
    const runtime = parseRuntimeInput(targetRuntime, story.target_duration_sec || 60)
    return Math.max(6, Math.round(runtime / Math.max(1, chapters.length + 1)))
  }

  function openChapterCreator() {
    const slot = chapters.length + 1
    setChapterOrderSlot(slot)
    setChapterDraft(makeChapterIntakeDraft(slot - 1, newChapterDuration()))
    setStructureError(null)
    setChapterCreatorOpen(true)
  }

  const updateChapterDraft = <Key extends keyof ChapterIntakeDraft>(
    key: Key,
    value: ChapterIntakeDraft[Key],
  ) => {
    setChapterDraft((current) => ({ ...current, [key]: value }))
  }

  function chapterSummaryFromDraft(draft: ChapterIntakeDraft): string | null {
    const parts = [
      draft.summary.trim(),
      draft.sourcePrompt.trim() ? `Source prompt: ${draft.sourcePrompt.trim()}` : '',
      draft.productionNotes.trim() ? `Production notes: ${draft.productionNotes.trim()}` : '',
    ].filter(Boolean)
    return parts.length ? parts.join('\n\n') : null
  }

  async function createChapterFromDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const targetIndex = Math.max(
      0,
      Math.min(chapters.length, Math.round(Number(chapterOrderSlot) || chapters.length + 1) - 1),
    )
    const title = chapterDraft.title.trim() || `Chapter ${targetIndex + 1}`
    let createdChapterId = ''
    const success = await persistStructure(
      async () => {
        const created = await api.createChapter(story.id, {
          title,
          summary: chapterSummaryFromDraft(chapterDraft),
          order_index: chapters.length,
          narrative_purpose: chapterDraft.narrativePurpose.trim() || null,
          target_duration_sec: chapterDraft.targetDurationSec,
          dramatic_progression: chapterDraft.dramaticProgression.trim() || null,
        })
        createdChapterId = created.id
        if (targetIndex < chapters.length) {
          const orderedIds = chapters.map((chapter) => chapter.id)
          orderedIds.splice(targetIndex, 0, created.id)
          await api.reorderChapters(story.id, orderedIds)
        }
      },
      `Chapter "${title}" created at ${chapterCode(targetIndex)}.`,
    )
    if (!success) return
    setChapterCreatorOpen(false)
    if (createdChapterId) {
      setExpanded((ids) => (ids.includes(createdChapterId) ? ids : [...ids, createdChapterId]))
    }
  }

  async function editChapter(chapter: Chapter) {
    const title = window.prompt('Chapter title', chapter.title)
    if (title === null || !title.trim()) return
    const summary = window.prompt('Chapter summary (optional)', chapter.summary ?? '')
    if (summary === null) return
    await persistStructure(
      () => api.updateChapter(chapter.id, { title: title.trim(), summary: summary.trim() || null }),
      `Chapter “${title.trim()}” updated on the backend.`,
    )
  }

  async function editScene(scene: Scene) {
    const title = window.prompt('Scene title', scene.title)
    if (title === null || !title.trim()) return
    const summary = window.prompt('Scene summary (optional)', scene.summary ?? '')
    if (summary === null) return
    await persistStructure(
      () => api.updateScene(scene.id, { title: title.trim(), summary: summary.trim() || null }),
      `Scene “${title.trim()}” updated on the backend.`,
    )
  }

  async function deleteChapter(chapter: Chapter) {
    if (!window.confirm(`Archive chapter “${chapter.title}” and its active descendants?`)) return
    await persistStructure(
      () => api.deleteChapter(chapter.id, 'Archived from Story & chapters.'),
      `Chapter “${chapter.title}” archived on the backend.`,
    )
  }

  async function deleteScene(scene: Scene) {
    if (!window.confirm(`Archive scene “${scene.title}” and its active shots?`)) return
    await persistStructure(
      () => api.deleteScene(scene.id, 'Archived from Story & chapters.'),
      `Scene “${scene.title}” archived on the backend.`,
    )
  }

  async function moveChapter(chapterIndex: number, direction: -1 | 1) {
    await moveChapterTo(chapterIndex, chapterIndex + direction)
  }

  async function moveChapterTo(chapterIndex: number, targetIndex: number) {
    if (targetIndex < 0 || targetIndex >= chapters.length || targetIndex === chapterIndex) return
    const orderedIds = chapters.map((chapter) => chapter.id)
    const [chapterId] = orderedIds.splice(chapterIndex, 1)
    if (!chapterId) return
    orderedIds.splice(targetIndex, 0, chapterId)
    await persistStructure(
      () => api.reorderChapters(story.id, orderedIds),
      `Chapter moved to ${chapterCode(targetIndex)}.`,
    )
  }

  async function moveScene(chapter: Chapter, sceneIndex: number, direction: -1 | 1) {
    const targetIndex = sceneIndex + direction
    if (targetIndex < 0 || targetIndex >= chapter.scenes.length) return
    const orderedIds = chapter.scenes.map((scene) => scene.id)
    ;[orderedIds[sceneIndex], orderedIds[targetIndex]] = [
      orderedIds[targetIndex],
      orderedIds[sceneIndex],
    ]
    await persistStructure(
      () => api.reorderScenes(chapter.id, orderedIds),
      'Scene order persisted to the backend.',
    )
  }

  const sceneCount = chapters.reduce((n, ch) => n + ch.scenes.length, 0)
  const shotCount = chapters.reduce(
    (n, ch) => n + ch.scenes.reduce((s, sc) => s + sc.shots.length, 0),
    0,
  )
  const plannedSec = chapters.reduce(
    (n, ch) =>
      n +
      ch.scenes.reduce(
        (s, sc) => s + sc.shots.reduce((t, sh) => t + (sh.duration_sec || 0), 0),
        0,
      ),
    0,
  )
  const selectedProposalSummary = selectedProposal
    ? proposalPayloadSummary(selectedProposal.payload)
    : null

  function chapterCode(index: number) {
    return `CH${String(index + 1).padStart(2, '0')}`
  }
  function sceneCode(index: number) {
    return `SC${String(index + 1).padStart(2, '0')}`
  }

  async function saveStoryIntake() {
    await updateStoryFields({
      title: title.trim(),
      logline: logline || null,
      synopsis: synopsis || null,
      base_story: baseStory,
      audience: audience || null,
      tone: tone || null,
      genre: genre || null,
      visual_style: visualStyle || null,
      point_of_view: pointOfView || null,
      production_notes: productionNotes || null,
      target_duration_sec: parseRuntimeInput(targetRuntime, story.target_duration_sec),
    })
  }

  function openPlanningOrchestration() {
    const details = planningDetailsRef.current
    if (details) {
      details.open = true
      window.requestAnimationFrame(() => {
        details.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }
    setPlanningNotice(
      'Configure a factual provider route and create a backend planning run. No hierarchy was changed.',
    )
    setMessage('Planning orchestration opened. No structure was generated or applied.')
  }

  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">STORY INTAKE &amp; STRUCTURE</span>
          <h1>Story &amp; chapters</h1>
          <p>Edit the source narrative and reconcile every structural beat before shot planning.</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn secondary"
            disabled={planningBusy || busy}
            onClick={() => openPlanningOrchestration()}
          >
            <span>Open planning orchestration</span>
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => {
              void saveStoryIntake()
              setMessage('Story structure marked reviewed')
            }}
          >
            <span>Mark reviewed</span>
          </button>
        </div>
      </div>

      <div className="split-layout story-editor">
        <div className="stack">
          <section className="panel">
            <header className="panel-head">
              <div>
                <h2>Source story</h2>
                <p>Production intent supplied to the selected orchestrator.</p>
              </div>
            </header>
            <div className="form-grid two">
              <label>
                Title
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  required
                  maxLength={300}
                />
              </label>
              <label>
                Target runtime
                <input
                  type="text"
                  inputMode="numeric"
                  value={targetRuntime}
                  disabled={busy}
                  onChange={(e) => setTargetRuntime(e.target.value)}
                  placeholder="540 or 9:00"
                />
                <small className="form-hint">
                  Plain numbers are seconds. You can also type minutes:seconds, e.g. 9:00.
                </small>
              </label>
            </div>
            <div className="form-stack">
              <label>
                Logline
                <textarea value={logline} disabled={busy} onChange={(e) => setLogline(e.target.value)} />
              </label>
              <label>
                Full base story
                <textarea
                  className="story-textarea"
                  value={baseStory}
                  disabled={busy}
                  onChange={(e) => setBaseStory(e.target.value)}
                />
              </label>
              <label>
                Synopsis
                <textarea value={synopsis} disabled={busy} onChange={(e) => setSynopsis(e.target.value)} />
              </label>
              <div className="form-grid three">
                <label>
                  Audience
                  <input value={audience} disabled={busy} onChange={(e) => setAudience(e.target.value)} />
                </label>
                <label>
                  Tone
                  <input value={tone} disabled={busy} onChange={(e) => setTone(e.target.value)} />
                </label>
                <label>
                  Genre
                  <input value={genre} disabled={busy} onChange={(e) => setGenre(e.target.value)} />
                </label>
              </div>
              <div className="form-grid two">
                <label>
                  Visual style
                  <input value={visualStyle} disabled={busy} onChange={(e) => setVisualStyle(e.target.value)} />
                </label>
                <label>
                  Narrative point of view
                  <input value={pointOfView} disabled={busy} onChange={(e) => setPointOfView(e.target.value)} />
                </label>
              </div>
              <label>
                Production notes
                <textarea
                  value={productionNotes}
                  disabled={busy}
                  onChange={(e) => setProductionNotes(e.target.value)}
                />
              </label>
              <div className="page-actions">
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy}
                  onClick={() => void saveStoryIntake()}
                >
                  <span>Save story fields</span>
                </button>
              </div>
            </div>
          </section>

          <section className="panel">
            <header className="panel-head">
              <div>
                <h2>Narrative hierarchy</h2>
                <p>
                  {chapters.length} chapters · {sceneCount} scenes · {shotCount} shots ·{' '}
                  {formatDuration(parseRuntimeInput(targetRuntime, story.target_duration_sec))} target
                </p>
              </div>
              <button
                type="button"
                className="btn quiet"
                disabled={structureDisabled}
                onClick={() => openChapterCreator()}
              >
                <span>Add chapter</span>
              </button>
            </header>
            {chapterCreatorOpen ? (
              <form className="chapter-creator-panel" onSubmit={createChapterFromDraft}>
                <header className="chapter-creator-head">
                  <div>
                    <span className="eyebrow">NEW CHAPTER</span>
                    <h3>Chapter intake</h3>
                    <p>Use the same three-step setup as a new project, then place the chapter in the live order.</p>
                  </div>
                  <label className="chapter-order-slot">
                    <span>Insert as</span>
                    <select
                      aria-label="New chapter order slot"
                      disabled={structureDisabled}
                      value={chapterOrderSlot}
                      onChange={(event) => setChapterOrderSlot(Number(event.target.value))}
                    >
                      {Array.from({ length: chapters.length + 1 }, (_, index) => (
                        <option key={index} value={index + 1}>
                          {chapterCode(index)} {index < chapters.length ? `before ${chapters[index].title}` : 'at end'}
                        </option>
                      ))}
                    </select>
                  </label>
                </header>
                <ChapterIntakeForm
                  draft={chapterDraft}
                  index={Math.max(0, chapterOrderSlot - 1)}
                  disabled={structureDisabled}
                  onChange={updateChapterDraft}
                />
                <footer className="chapter-creator-actions">
                  <button
                    type="button"
                    className="btn secondary"
                    disabled={structureDisabled}
                    onClick={() => setChapterCreatorOpen(false)}
                  >
                    <span>Cancel</span>
                  </button>
                  <button type="submit" className="btn primary" disabled={structureDisabled}>
                    <span>Create chapter</span>
                  </button>
                </footer>
              </form>
            ) : null}
            {structureError ? (
              <p className="notice error" role="alert">
                {structureError}
              </p>
            ) : null}
            {!chapters.length ? (
              <EmptyState title="No chapters" detail="Create the first chapter to structure the story." />
            ) : (
              <div className="hierarchy">
                {chapters.map((chapter, chapterIndex) => {
                  const open = expanded.includes(chapter.id)
                  const code = chapterCode(chapterIndex)
                  return (
                    <article key={chapter.id}>
                      <header>
                        <button
                          type="button"
                          onClick={() =>
                            setExpanded((ids) =>
                              open ? ids.filter((id) => id !== chapter.id) : [...ids, chapter.id],
                            )
                          }
                        >
                          <span className="hierarchy-chevron" aria-hidden="true">
                            {open ? '▾' : '▸'}
                          </span>
                          <span>
                            <small>{code}</small>
                            <b>{chapter.title}</b>
                          </span>
                        </button>
                        <span>
                          <b>{formatDuration(chapter.duration_sec)}</b>
                          <small>
                            {chapter.scenes.length} scene{chapter.scenes.length === 1 ? '' : 's'}
                          </small>
                        </span>
                        <div>
                          <label className="chapter-order-select">
                            <span>Slot</span>
                            <select
                              aria-label={`Move ${chapter.title} to chapter slot`}
                              disabled={structureDisabled || chapters.length < 2}
                              value={chapterIndex + 1}
                              onChange={(event) => void moveChapterTo(chapterIndex, Number(event.target.value) - 1)}
                            >
                              {chapters.map((_, index) => (
                                <option key={index} value={index + 1}>
                                  {chapterCode(index)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            disabled={structureDisabled || chapterIndex === 0}
                            aria-label="Move chapter up"
                            onClick={() => void moveChapter(chapterIndex, -1)}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            disabled={structureDisabled || chapterIndex === chapters.length - 1}
                            aria-label="Move chapter down"
                            onClick={() => void moveChapter(chapterIndex, 1)}
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            disabled={structureDisabled}
                            aria-label="Edit chapter"
                            onClick={() => void editChapter(chapter)}
                          >
                            ✎
                          </button>
                          <button
                            type="button"
                            disabled={structureDisabled}
                            aria-label="Archive chapter"
                            onClick={() => void deleteChapter(chapter)}
                          >
                            ⌫
                          </button>
                        </div>
                      </header>
                      {open ? (
                        <div className="hierarchy-scenes">
                          {chapter.scenes.map((scene, sceneIndex) => (
                            <div key={scene.id}>
                              <span className="scene-index">{sceneIndex + 1}</span>
                              <span>
                                <small>{sceneCode(sceneIndex)}</small>
                                <b>{scene.title}</b>
                                <p>{scene.summary || 'No scene purpose yet.'}</p>
                                <em>
                                  {scene.shots[0]?.location ||
                                    scene.summary?.slice(0, 48) ||
                                    'Location TBD'}
                                </em>
                              </span>
                              <span>
                                <b>{scene.duration_sec} sec</b>
                                <small>
                                  {scene.shots.length} shot{scene.shots.length === 1 ? '' : 's'}
                                </small>
                              </span>
                              <span className="character-dots" aria-hidden="true" />
                              <button
                                type="button"
                                disabled={structureDisabled || sceneIndex === 0}
                                aria-label={`Move ${scene.title} up`}
                                onClick={() => void moveScene(chapter, sceneIndex, -1)}
                              >
                                ↑
                              </button>
                              <button
                                type="button"
                                disabled={
                                  structureDisabled || sceneIndex === chapter.scenes.length - 1
                                }
                                aria-label={`Move ${scene.title} down`}
                                onClick={() => void moveScene(chapter, sceneIndex, 1)}
                              >
                                ↓
                              </button>
                              <button
                                type="button"
                                disabled={structureDisabled}
                                aria-label={`Edit ${scene.title}`}
                                onClick={() => void editScene(scene)}
                              >
                                ✎
                              </button>
                              <button
                                type="button"
                                disabled={structureDisabled}
                                aria-label={`Archive ${scene.title}`}
                                onClick={() => void deleteScene(scene)}
                              >
                                ⌫
                              </button>
                              <button
                                type="button"
                                disabled={structureDisabled}
                                aria-label="Add shot under scene"
                                onClick={() => void addHierarchy('shot')}
                              >
                                +
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  )
                })}
              </div>
            )}
            <div className="story-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn secondary"
                disabled={structureDisabled}
                onClick={() => void addHierarchy('scene')}
              >
                <span>Add scene</span>
              </button>
              <button
                type="button"
                className="btn secondary"
                disabled={structureDisabled}
                onClick={() => void addHierarchy('shot')}
              >
                <span>Add shot</span>
              </button>
            </div>
          </section>
        </div>

        <aside className="suggestion-panel">
          <header>
            <span className="orchestrator-mark" aria-hidden="true">
              ✦
            </span>
            <div>
              <span className="eyebrow">ORCHESTRATOR SUGGESTIONS</span>
              <h2>
                {proposals.length
                  ? `${proposals.length} backend proposal${proposals.length === 1 ? '' : 's'}`
                  : 'No backend proposal loaded'}
              </h2>
            </div>
          </header>
          {proposals.length ? (
            <div className="suggestions">
              {proposals.slice(0, 3).map((proposal, i) => (
                <article key={proposal.id}>
                  <span>{i + 1}</span>
                  <div>
                    <b>{proposal.proposal_type.replaceAll('_', ' ')}</b>
                    <p>
                      Status: {proposal.status} · Validation:{' '}
                      {proposal.validation_status ?? 'not evaluated'}
                    </p>
                    <small>Immutable backend proposal {shortId(proposal.id)}</small>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      void chooseProposal(proposal.id)
                      openPlanningOrchestration()
                    }}
                  >
                    Inspect
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="suggestion-empty">
              <p>
                Create a backend planning run to produce an immutable proposal. Nothing changes
                until a validated proposal is reviewed and explicitly applied.
              </p>
              <button
                type="button"
                className="btn secondary"
                disabled={planningBusy || busy}
                onClick={() => openPlanningOrchestration()}
              >
                <span>Open planning orchestration</span>
              </button>
            </div>
          )}
          <div className="proposal-summary">
            <span>Current structure</span>
            <b>
              {chapters.length} chapters · {sceneCount} scenes · {shotCount} shots
            </b>
            <small>
              {plannedSec} of {parseRuntimeInput(targetRuntime, story.target_duration_sec)} planned seconds.
            </small>
          </div>
        </aside>
      </div>

      <details
        ref={planningDetailsRef}
        className="legacy-story-ops backend-diagnostics"
        style={{ marginTop: 16 }}
      >
        <summary>
          <span className="eyebrow">PLANNING ORCHESTRATION</span>
          <span>
            Backend runs, proposals, and apply gates (secondary · not Sites primary chrome)
          </span>
        </summary>
        <div className="legacy-story-ops-body">
      <section className="panel" aria-labelledby="planning-orchestration-title" style={{ marginTop: 14 }}>
        <div className="panel-title">
          <div>
            <h2 id="planning-orchestration-title">Planning generation and iterations</h2>
            <p>
              Fast bypass is the default: generate phases 1–5, inspect the draft, then apply,
              edit, reject, or generate a new iteration.
            </p>
          </div>
          <div className="inline-actions">
            <span className="truth-pill">{runs.length} run{runs.length === 1 ? '' : 's'}</span>
            <span className="truth-pill">{proposals.length} proposal{proposals.length === 1 ? '' : 's'}</span>
            <button
              type="button"
              className="ghost-button touch-target"
              disabled={disabled}
              onClick={() => void loadPlanning(selectedRunId || undefined, selectedProposalId || undefined)}
            >
              Refresh status
            </button>
          </div>
        </div>

        {planningLoading ? <LoadingState title="Loading planning history…" /> : null}
        {planningError ? (
          <p className="notice error" role="alert">
            {planningError}
          </p>
        ) : null}
        {planningNotice ? (
          <p className="notice info" role="status" aria-live="polite">
            {planningNotice}
          </p>
        ) : null}

        <div className="split-2">
          <div className="stack-form" style={{ maxWidth: '100%' }}>
            <h3>1. Configure and run</h3>
            <label className="check-card">
              <input
                type="checkbox"
                checked={bypassPlanningGates}
                onChange={(event) => setBypassPlanningGates(event.target.checked)}
                disabled={disabled}
              />
              <span>
                <b>Fast planning bypass</b>
                <small>
                  Default. Auto-start planning runs, allow direct application of usable drafts,
                  and make new iterations from completed runs.
                </small>
              </span>
            </label>
            <label>
              Audit name
              <input
                value={actorName}
                onChange={(event) => setActorName(event.target.value)}
                disabled={disabled}
                placeholder="Your name or production role"
                maxLength={200}
              />
            </label>
            <div className="split-2">
              <label>
                Routing mode
                <select
                  value={isAgentless ? 'automatic' : routingMode}
                  onChange={(event) =>
                    changeRoutingMode(event.target.value as OrchestrationRoutingMode)
                  }
                  disabled={disabled || isAgentless}
                >
                  <option value="automatic">Automatic</option>
                  {!isAgentless ? <option value="hybrid">Hybrid</option> : null}
                  {!isAgentless ? <option value="manual">Manual</option> : null}
                </select>
              </label>
              <label>
                Provider preference
                <select
                  value={isAgentless ? 'local' : providerPreference}
                  onChange={(event) => setProviderPreference(event.target.value as ProviderPreference)}
                  disabled={disabled || isAgentless}
                >
                  <option value="local">Prefer local only</option>
                  {!isAgentless ? <option value="mixed">Prefer local and allow hosted</option> : null}
                  {!isAgentless ? <option value="hosted">Prefer hosted only</option> : null}
                </select>
              </label>
            </div>
            <p className="form-hint">
              {isAgentless
                ? `This project is locked to the selected local ${LOCAL_AGENT_LABELS[planningAgent] ?? planningAgent} agent. Prompts are structured JSON; hosted/API and mock fallbacks are blocked.`
                : 'Provider preferences are recorded with the run. This page does not install models, submit render jobs, or generate media.'}
            </p>
            <div className="split-2">
              <label>
                Max steps
                <input
                  type="number"
                  min={10}
                  max={50}
                  value={maxSteps}
                  onChange={(event) => setMaxSteps(Number(event.target.value))}
                  disabled={disabled}
                />
              </label>
              <label>
                Repair budget
                <input
                  type="number"
                  min={0}
                  max={20}
                  value={repairBudget}
                  onChange={(event) => setRepairBudget(Number(event.target.value))}
                  disabled={disabled}
                />
              </label>
              <label>
                Time budget seconds
                <input
                  type="number"
                  min={30}
                  max={3600}
                  value={timeBudgetSec}
                  onChange={(event) => setTimeBudgetSec(Number(event.target.value))}
                  disabled={disabled}
                />
              </label>
              <label>
                Transport retries
                <input
                  type="number"
                  min={0}
                  max={5}
                  value={transportRetryLimit}
                  onChange={(event) => setTransportRetryLimit(Number(event.target.value))}
                  disabled={disabled}
                />
              </label>
            </div>
            {routingMode !== 'automatic' ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Task</th><th>Route</th><th>Runtime fact</th></tr>
                  </thead>
                  <tbody>
                    {PLANNING_TASKS.map(({ task, label, logicalModel }) => {
                      const selected = manualRouteSelections[task] ?? ''
                      const option = routeOptions.find((item) => item.value === selected)
                      return (
                        <tr key={task}>
                          <td>{label} · {logicalModel}</td>
                          <td>
                            <select
                              value={selected}
                              onChange={(event) =>
                                setManualRouteSelections((current) => ({
                                  ...current,
                                  [task]: event.target.value,
                                }))
                              }
                              disabled={disabled}
                            >
                              <option value="">{routingMode === 'manual' ? 'Route required' : 'Use automatic route'}</option>
                              {routeOptions.map((item) => (
                                <option key={`${task}-${item.value}`} value={item.value}>
                                  {item.label}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>{option ? `${option.providerIdentifier} · ${option.availabilityStatus} · ${option.privacy}` : 'Automatic decision'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
            {visibleProviderFacts.length ? (
              <details className="debug-panel">
                <summary>Provider facts used by preflight</summary>
                <ul>
                  {visibleProviderFacts.map((provider) => (
                    <li key={provider.provider_identifier}>
                      {provider.display_name}: {provider.availability_status} · {provider.privacy_classification} · {provider.capabilities.join(', ') || 'no verified capabilities'}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {routingPreflight ? (
              <p className={`notice ${routingPreflight.valid ? 'info' : 'error'}`} role="status">
                Routing preflight {routingPreflight.valid ? 'passed' : 'failed'} with {routingPreflight.routes.length} route{routingPreflight.routes.length === 1 ? '' : 's'}.
              </p>
            ) : null}
            <div className="inline-actions">
              <button type="button" className="secondary-button" disabled={disabled} onClick={() => void createRun()}>
                {bypassPlanningGates ? 'Generate planning draft' : 'Create pending run'}
              </button>
              {!bypassPlanningGates ? (
                <button
                  type="button"
                  className="primary-button"
                  disabled={disabled || !runCanStart}
                  onClick={() => void startRun()}
                >
                  Start selected run
                </button>
              ) : null}
              <button
                type="button"
                className="ghost-button"
                disabled={disabled || !runCanCancel}
                onClick={() => void cancelRun()}
              >
                Cancel selected run
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={disabled || !runCanIterate}
                onClick={() => void retryRun()}
              >
                {bypassPlanningGates ? 'Generate new iteration' : 'Create retry run'}
              </button>
            </div>

            <label>
              Planning run
              <select
                value={selectedRunId}
                onChange={(event) => void chooseRun(event.target.value)}
                disabled={disabled || !runs.length}
              >
                {!runs.length ? <option value="">No runs yet</option> : null}
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.status} · {formatDate(run.created_at)} · {shortId(run.id)}
                  </option>
                ))}
              </select>
            </label>

            {selectedRun ? (
              <>
                <ul className="kv-list">
                  <li>
                    <span>Status</span>
                    <strong><span className={`truth-pill ${statusClass(selectedRun.status)}`}>{selectedRun.status}</span></strong>
                  </li>
                  <li>
                    <span>Progress</span>
                    <strong>
                      {selectedRun.steps.filter((step) => step.status === 'completed').length} /{' '}
                      {selectedRun.max_steps} steps
                    </strong>
                  </li>
                  <li><span>Repairs used</span><strong>{selectedRun.repair_used} / {selectedRun.repair_budget}</strong></li>
                  <li><span>Requested by</span><strong>{selectedRun.requested_by || 'Not recorded'}</strong></li>
                  <li><span>Created</span><strong>{formatDate(selectedRun.created_at)}</strong></li>
                </ul>
                {selectedRun.failure_message ? (
                  <p className="notice error" role="alert">{selectedRun.failure_message}</p>
                ) : null}
                {selectedRun.steps.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Step</th><th>Status</th><th>Route</th><th>Attempt</th></tr>
                      </thead>
                      <tbody>
                        {selectedRun.steps.map((step) => (
                          <tr key={step.id}>
                            <td>{step.sequence_index + 1}. {step.task_type}</td>
                            <td><span className={`truth-pill ${statusClass(step.status)}`}>{step.status}</span></td>
                            <td>{formatPlanningRoute(step, providerCatalog)}</td>
                            <td>{step.attempt_number}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="form-hint">This run has no persisted steps yet.</p>
                )}
              </>
            ) : null}
          </div>

          <div className="stack-form" style={{ maxWidth: '100%' }}>
            <h3>2. Inspect and decide</h3>
            <label>
              Proposal
              <select
                value={selectedProposalId}
                onChange={(event) => void chooseProposal(event.target.value)}
                disabled={disabled || !proposals.length}
              >
                {!proposals.length ? <option value="">No proposals yet</option> : null}
                {proposals.map((proposal) => (
                  <option key={proposal.id} value={proposal.id}>
                    {proposal.status} · {proposal.proposal_type} · {shortId(proposal.id)}
                  </option>
                ))}
              </select>
            </label>

            {selectedProposal ? (
              <>
                <ul className="kv-list">
                  <li>
                    <span>Status</span>
                    <strong><span className={`truth-pill ${statusClass(selectedProposal.status)}`}>{selectedProposal.status}</span></strong>
                  </li>
                  <li>
                    <span>Validation</span>
                    <strong><span className={`truth-pill ${statusClass(selectedProposal.validation_status)}`}>{selectedProposal.validation_status || 'unknown'}</span></strong>
                  </li>
                  <li><span>Schema</span><strong>{selectedProposal.schema_name || 'Not recorded'}</strong></li>
                  <li><span>Reviewed by</span><strong>{selectedProposal.reviewed_by || 'Not reviewed'}</strong></li>
                  <li><span>Content hash</span><strong className="mono">{selectedProposal.content_hash ? shortId(selectedProposal.content_hash) : 'Not recorded'}</strong></li>
                  <li><span>Diff operations</span><strong>{proposalDiff?.ops.length ?? 'Unavailable'}</strong></li>
                </ul>

                {selectedProposal.validation_errors.length ? (
                  <div className="notice error" role="alert">
                    <strong>Validation errors</strong>
                    <ul>{selectedProposal.validation_errors.map((item, index) => <li key={`${index}-${String(item)}`}>{String(item)}</li>)}</ul>
                  </div>
                ) : null}
                {selectedProposal.warnings_json.length ? (
                  <div className="notice warning">
                    <strong>Proposal warnings</strong>
                    <ul>{selectedProposal.warnings_json.map((item, index) => <li key={`${index}-${String(item)}`}>{String(item)}</li>)}</ul>
                  </div>
                ) : null}

                {proposalDiff ? (
                  proposalDiff.ops.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Change</th><th>Path</th><th>Before</th><th>After</th></tr></thead>
                        <tbody>
                          {proposalDiff.ops.map((operation, index) => (
                            <tr key={`${operation.op}-${operation.path}-${index}`}>
                              <td>{operation.op}</td>
                              <td className="mono">{operation.path}</td>
                              <td>{diffValue(operation.before)}</td>
                              <td>{diffValue(operation.after)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="notice info">The proposal diff contains no changes.</p>
                  )
                ) : (
                  <p className="notice warning">
                    Proposal diff is unavailable. Fast bypass can still apply if backend revalidation passes.
                  </p>
                )}

                {selectedProposalSummary ? (
                  <div className="debug-panel">
                    <div className="panel-title">
                      <div>
                        <h3>Proposal payload summary</h3>
                        <p>
                          Full immutable JSON is hidden during normal editing. Copy or download it only
                          when you need the raw artifact.
                        </p>
                      </div>
                      <div className="inline-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={disabled}
                          onClick={() => void copyProposalPayload()}
                        >
                          Copy JSON
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={disabled}
                          onClick={() => downloadProposalPayload()}
                        >
                          Download JSON
                        </button>
                      </div>
                    </div>
                    <ul className="kv-list">
                      <li><span>Title</span><strong>{selectedProposalSummary.title}</strong></li>
                      <li><span>Target runtime</span><strong>{selectedProposalSummary.targetDuration}</strong></li>
                      <li><span>Chapters</span><strong>{selectedProposalSummary.chapters}</strong></li>
                      <li><span>Scenes</span><strong>{selectedProposalSummary.scenes}</strong></li>
                      <li><span>Shots</span><strong>{selectedProposalSummary.shots}</strong></li>
                      <li><span>Characters</span><strong>{selectedProposalSummary.characters}</strong></li>
                      <li><span>Payload size</span><strong>{selectedProposalSummary.payloadSize}</strong></li>
                    </ul>
                  </div>
                ) : null}

                <label>
                  Review notes (optional)
                  <textarea
                    value={reviewNotes}
                    onChange={(event) => setReviewNotes(event.target.value)}
                    disabled={disabled || proposalIsTerminal}
                    maxLength={4000}
                    placeholder="Record approval context or requested follow-up"
                  />
                </label>
                <label>
                  Rejection reason (required only to reject)
                  <textarea
                    value={rejectionReason}
                    onChange={(event) => setRejectionReason(event.target.value)}
                    disabled={disabled || proposalIsTerminal}
                    maxLength={4000}
                    placeholder="Explain why this proposal must not be applied"
                  />
                </label>

                <div className="inline-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={disabled || !proposalCanReview}
                    onClick={() => void reviewProposal()}
                  >
                    Save review note
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={disabled || !rejectionReason.trim() || proposalIsTerminal}
                    onClick={() => void rejectProposal()}
                  >
                    Reject proposal
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    disabled={disabled || !proposalCanApply}
                    onClick={() => void applyProposal()}
                  >
                    Apply generated draft
                  </button>
                </div>
                <p className="form-hint">
                  Apply still checks validation, ownership, and stale-base safety, then refreshes the
                  live Studio snapshot. It does not create video render jobs.
                </p>
              </>
            ) : (
              <EmptyState
                title="No planning draft yet"
                detail="Generate a planning draft. Fast bypass auto-starts it and publishes the usable proposal here."
              />
            )}
          </div>
        </div>
      </section>

        </div>
      </details>
    </div>
  )
}
