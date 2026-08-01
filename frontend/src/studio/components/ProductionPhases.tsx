import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import {
  api,
  type PhaseOnePackage,
  type PhaseVersionDetail,
  type PhaseVersionSummary,
  type ProjectStoryboardSettings,
  type ProductionPipeline,
  type RuntimeCatalogWorkflowTemplate,
  type StartingImageGenerateRequest,
  type StoryboardAggregate,
} from '../../api/client'
import type { PageId } from '../../components/AppShell'
import type { PlanningAgent } from '../../planningAgents'
import { ErrorNotice } from '../../components/Cards'
import { ProductionPhasePreview } from './ProductionPhasePreview'
import { LoadingState } from './StateBlocks'
import {
  snapshotMetricsFromWorkspace,
  workspaceFromAggregate,
  workspaceFromHistoricalDetail,
} from '../snapshotWorkspace'
import { formatDuration } from '../utils'

type EditablePhaseOne = Pick<
  PhaseOnePackage,
  | 'project_title'
  | 'logline'
  | 'short_synopsis'
  | 'detailed_treatment'
  | 'complete_script'
  | 'narration_script'
  | 'dialogue_script'
  | 'non_dialogue_action'
  | 'silent_visual_beats'
  | 'emotional_progression'
  | 'dramatic_escalation'
  | 'source_fidelity_notes'
  | 'creative_assumptions'
>

/** Canonical Phase 1 script package schema from the production API. */
const PHASE_ONE_PACKAGE_SCHEMA = 'cineforge.phase_one_script_package'
const DEFAULT_PHASE_FIVE_WORKFLOW = '__configured_phase6_flux2__'

type QueueProgress = {
  completed: number
  total: number
  message: string
}

function isPhaseOnePackage(value: unknown): value is PhaseOnePackage {
  if (!value || typeof value !== 'object') return false
  const row = value as Record<string, unknown>
  // Match Transfiguration / generated heads: schema plus fields the Phase 1 workspace renders.
  if (row.schema_name !== PHASE_ONE_PACKAGE_SCHEMA) return false
  if (typeof row.project_title !== 'string') return false
  if (typeof row.logline !== 'string') return false
  if (!row.duration_analysis || typeof row.duration_analysis !== 'object') return false
  return true
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
}

function stateLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function listText(items: string[]) {
  return items.join('\n')
}

function textList(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function downloadText(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function selectedPlanningAgent(
  settings: ProjectStoryboardSettings | null,
): PlanningAgent {
  return settings?.prompting_policy_json.planning_agent === 'sulphur'
    ? 'sulphur'
    : 'qwen'
}

type ProductionPhasesProps = {
  storyId: string
  projectId?: string
  data?: StoryboardAggregate | null
  onNavigate?: (page: PageId) => void
}

export function ProductionPhases({
  storyId,
  projectId,
  data = null,
  onNavigate,
}: ProductionPhasesProps) {
  const [pipeline, setPipeline] = useState<ProductionPipeline | null>(null)
  const [productionSettings, setProductionSettings] = useState<ProjectStoryboardSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState<EditablePhaseOne | null>(null)
  const [selectedPhaseNumber, setSelectedPhaseNumber] = useState(1)
  const [versionsByPhase, setVersionsByPhase] = useState<Record<number, PhaseVersionSummary[]>>({})
  const [selectedByPhase, setSelectedByPhase] = useState<Partial<Record<number, string>>>({})
  const [loadedDetail, setLoadedDetail] = useState<PhaseVersionDetail | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [compare, setCompare] = useState(false)
  const [iterationLabel, setIterationLabel] = useState('')
  const [iterationNotes, setIterationNotes] = useState('')
  const [savingIteration, setSavingIteration] = useState(false)
  const [approvingPhase, setApprovingPhase] = useState(false)
  const [workingPhaseNumber, setWorkingPhaseNumber] = useState<number | null>(null)
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null)
  const [workflowOpen, setWorkflowOpen] = useState(false)
  const [workflowTemplates, setWorkflowTemplates] = useState<RuntimeCatalogWorkflowTemplate[]>([])
  const [workflowSelection, setWorkflowSelection] = useState(DEFAULT_PHASE_FIVE_WORKFLOW)
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [workflowError, setWorkflowError] = useState<string | null>(null)
  const [workflowUploadName, setWorkflowUploadName] = useState('')
  const [workflowUploadJson, setWorkflowUploadJson] = useState<Record<string, unknown> | null>(null)
  const [queueProgress, setQueueProgress] = useState<QueueProgress | null>(null)
  /** When the pipeline head is a non-package snapshot, hold the last script package from history. */
  const [packageFallback, setPackageFallback] = useState<PhaseOnePackage | null>(null)
  const phaseTabs = useRef<Array<HTMLButtonElement | null>>([])
  const iterationIdempotencyKey = useRef(`phase-iteration-${crypto.randomUUID()}`)
  const scopeKey = `${projectId ?? 'project'}:${storyId}:${selectedPhaseNumber}`

  const loadPhaseHistory = useCallback(async (phaseNumber: number) => {
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      const versions = await api.listPhaseVersions(storyId, phaseNumber)
      setVersionsByPhase((current) => ({ ...current, [phaseNumber]: versions }))
      return versions
    } catch (caught) {
      setHistoryError(
        caught instanceof Error ? caught.message : 'Unable to load retained phase history.',
      )
      return []
    } finally {
      setHistoryLoading(false)
    }
  }, [storyId])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await api.getProductionPipeline(storyId)
      setPipeline(next)
      // Clear version selection when story/project scope changes; keep phase number.
      // History rows are reloaded by the phase-history effect once pipeline is set —
      // do not wipe-and-forget them here or Phase 1 can keep only "Current draft".
      setSelectedByPhase({})
      setLoadedDetail(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the production phases.')
    } finally {
      setLoading(false)
    }
  }, [storyId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  useEffect(() => {
    let active = true
    if (!projectId) {
      const timer = window.setTimeout(() => {
        if (active) setProductionSettings(null)
      }, 0)
      return () => {
        active = false
        window.clearTimeout(timer)
      }
    }
    void api.getSettings(projectId)
      .then((settings) => {
        if (active) setProductionSettings(settings)
      })
      .catch(() => {
        if (active) setProductionSettings(null)
      })
    return () => { active = false }
  }, [projectId])

  useEffect(() => {
    let active = true
    // Async history list load when the project/story/phase scope changes.
    void (async () => {
      if (!pipeline) return
      setHistoryLoading(true)
      setHistoryError(null)
      try {
        const versions = await api.listPhaseVersions(storyId, selectedPhaseNumber)
        if (!active) return
        setVersionsByPhase((current) => ({ ...current, [selectedPhaseNumber]: versions }))
      } catch (caught) {
        if (!active) return
        setHistoryError(
          caught instanceof Error ? caught.message : 'Unable to load retained phase history.',
        )
      } finally {
        if (active) setHistoryLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [pipeline, selectedPhaseNumber, scopeKey, storyId])

  const phaseHistory = versionsByPhase[selectedPhaseNumber] ?? []
  const selectedIterationId = selectedByPhase[selectedPhaseNumber] ?? ''
  const selectedIteration = phaseHistory.find((item) => item.id === selectedIterationId) ?? null
  const phaseOneRegenerateIteration = selectedPhaseNumber === 1 && !selectedIteration
  const planningPhaseRegenerateIteration = selectedPhaseNumber >= 2 && selectedPhaseNumber <= 5 && !selectedIteration
  const generateIteration = phaseOneRegenerateIteration || planningPhaseRegenerateIteration

  useEffect(() => {
    let active = true
    const loadDetail = async () => {
      if (!selectedIterationId) {
        if (!active) return
        setLoadedDetail(null)
        setHistoryError(null)
        return
      }
      if (!active) return
      setHistoryLoading(true)
      setHistoryError(null)
      try {
        const detail = await api.getPhaseVersion(storyId, selectedPhaseNumber, selectedIterationId)
        if (!active) return
        // Reject stale responses from a different scope.
        if (
          detail.story_id !== storyId
          || detail.phase_number !== selectedPhaseNumber
          || (projectId && detail.project_id !== projectId)
        ) {
          setHistoryError('The retained iteration belongs to a different project, story, or phase.')
          setLoadedDetail(null)
          return
        }
        setLoadedDetail(detail)
      } catch (caught) {
        if (!active) return
        setLoadedDetail(null)
        setHistoryError(
          caught instanceof Error ? caught.message : 'The retained iteration failed integrity checks.',
        )
      } finally {
        if (active) setHistoryLoading(false)
      }
    }
    void loadDetail()
    return () => {
      active = false
    }
  }, [projectId, selectedIterationId, selectedPhaseNumber, storyId])

  useEffect(() => {
    const handleShortcut = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || document.querySelector('[role="dialog"]')) return
      if (!historyOpen && !createOpen && !workflowOpen && (event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 's') {
        event.preventDefault()
        iterationIdempotencyKey.current = `phase-iteration-${crypto.randomUUID()}`
        setCreateOpen(true)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [createOpen, historyOpen, workflowOpen])

  const phaseOne = pipeline?.phases.find((phase) => phase.phase_number === 1) ?? null
  const historical = Boolean(selectedIterationId && loadedDetail && !historyError)
  const historicalWorkspaceResult = useMemo(() => {
    if (!historical || !loadedDetail) return null
    return workspaceFromHistoricalDetail(loadedDetail, {
      storyId,
      projectId,
      phaseNumber: selectedPhaseNumber,
    })
  }, [historical, loadedDetail, projectId, selectedPhaseNumber, storyId])
  const historicalWorkspace = historicalWorkspaceResult?.workspace ?? null
  const historicalIsolationError = historicalWorkspaceResult?.error ?? null
  const incompleteReason = historicalIsolationError
    || (historicalWorkspace && !historicalWorkspace.completeness.complete
      ? historicalWorkspace.completeness.reason
      : null)
  const currentWorkspace = useMemo(() => {
    if (!data) return null
    return workspaceFromAggregate(data, selectedPhaseNumber)
  }, [data, selectedPhaseNumber])
  const packageData = useMemo(() => {
    if (historical && selectedPhaseNumber === 1) {
      // Prefer phase-one script package when present; never fall back to live draft.
      const output = loadedDetail?.output_json
      if (isPhaseOnePackage(output)) return output
      return null
    }
    if (historical) return null
    // Prefer latest if it is a script package; otherwise use history fallback.
    const latest = phaseOne?.latest_version?.output_json
    if (isPhaseOnePackage(latest)) return latest
    // Baselines / older manual retains may sit on the pipeline head while a prior
    // generated or revised script package remains in SQLite history.
    return packageFallback
  }, [historical, loadedDetail, packageFallback, phaseOne, selectedPhaseNumber])

  useEffect(() => {
    let active = true
    // Async IIFE so setState is not synchronous in the effect body
    // (react-hooks/set-state-in-effect). Matches the history-load pattern above.
    void (async () => {
      if (historical || selectedPhaseNumber !== 1) {
        if (active) setPackageFallback(null)
        return
      }
      const latest = phaseOne?.latest_version?.output_json
      if (isPhaseOnePackage(latest)) {
        if (active) setPackageFallback(null)
        return
      }
      const history = versionsByPhase[1] ?? []
      // Prefer generated/revision rows (package sources); also accept completed manual
      // retains that may carry a preserved package after the backend retain fix.
      // Walk newest-first until a real script package is found (skip non-package heads).
      const candidates = [...history]
        .reverse()
        .filter((item) => (
          item.source === 'generated'
          || item.source === 'revision'
          || item.source === 'imported'
          || item.completed
        ))
      if (!candidates.length) {
        if (active) setPackageFallback(null)
        return
      }
      for (const candidate of candidates) {
        try {
          const detail = await api.getPhaseVersion(storyId, 1, candidate.id)
          if (!active) return
          if (isPhaseOnePackage(detail.output_json)) {
            setPackageFallback(detail.output_json)
            return
          }
        } catch {
          // Try the next retained version.
        }
      }
      if (active) setPackageFallback(null)
    })()
    return () => {
      active = false
    }
  }, [historical, phaseOne?.latest_version?.output_json, selectedPhaseNumber, storyId, versionsByPhase])
  const qa = (!historical ? phaseOne?.latest_qa_report?.report_json : null) ?? null
  const selectedPhase = pipeline?.phases.find((phase) => phase.phase_number === selectedPhaseNumber) ?? null
  const displayPhase = selectedPhase && historical && loadedDetail
    ? {
        ...selectedPhase,
        latest_version: loadedDetail,
        current_version_number: loadedDetail.version_number,
      }
    : selectedPhase

  const selectPhase = (phaseNumber: number, focus = false) => {
    setSelectedPhaseNumber(phaseNumber)
    setApprovalNotice(null)
    setCompare(false)
    setEditing(false)
    if (focus) window.requestAnimationFrame(() => phaseTabs.current[phaseNumber - 1]?.focus())
  }

  const handlePhaseKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const phaseCount = pipeline?.phases.length || 8
    let nextIndex: number
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % phaseCount
    else if (event.key === 'ArrowLeft') nextIndex = (index + phaseCount - 1) % phaseCount
    else if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = phaseCount - 1
    else return
    event.preventDefault()
    selectPhase(nextIndex + 1, true)
  }

  const versionTimeline = [...phaseHistory.map((item) => item.id), '']
  const versionIndex = selectedIterationId
    ? Math.max(0, versionTimeline.indexOf(selectedIterationId))
    : versionTimeline.length - 1
  const moveVersion = (direction: -1 | 1) => {
    const next = Math.max(0, Math.min(versionTimeline.length - 1, versionIndex + direction))
    setSelectedByPhase((current) => ({
      ...current,
      [selectedPhaseNumber]: versionTimeline[next] || undefined,
    }))
    setCompare(false)
    setEditing(false)
  }

  const beginEdit = () => {
    if (!packageData || historical) return
    setDraft({
      project_title: packageData.project_title,
      logline: packageData.logline,
      short_synopsis: packageData.short_synopsis,
      detailed_treatment: packageData.detailed_treatment,
      complete_script: packageData.complete_script,
      narration_script: packageData.narration_script,
      dialogue_script: packageData.dialogue_script,
      non_dialogue_action: packageData.non_dialogue_action,
      silent_visual_beats: packageData.silent_visual_beats,
      emotional_progression: packageData.emotional_progression,
      dramatic_escalation: packageData.dramatic_escalation,
      source_fidelity_notes: packageData.source_fidelity_notes,
      creative_assumptions: packageData.creative_assumptions,
    })
    setEditing(true)
  }

  const saveRevision = async () => {
    if (!draft || !phaseOne?.current_version_number || historical) return
    setSaving(true)
    setError(null)
    try {
      const result = await api.revisePhaseOne(storyId, {
        ...draft,
        expected_version_number: phaseOne.current_version_number,
        requested_by: 'CineForge UI reviewer',
      })
      setPipeline(result.pipeline)
      setEditing(false)
      setDraft(null)
      await loadPhaseHistory(1)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save the Phase 1 revision.')
    } finally {
      setSaving(false)
    }
  }

  const saveIteration = async () => {
    const label = iterationLabel.trim()
    if (!label) {
      setHistoryError('Iteration label is required.')
      return
    }
    setSavingIteration(true)
    setWorkingPhaseNumber(selectedPhaseNumber)
    setHistoryError(null)
    try {
      if (selectedPhaseNumber === 1 && !selectedIteration && data?.story) {
        const result = await api.generatePhaseOne(storyId, {
          original_prompt:
            data.story.base_story
            || packageData?.detailed_treatment
            || packageData?.complete_script
            || packageData?.short_synopsis
            || data.story.title,
          planning_agent: selectedPlanningAgent(productionSettings),
          prompt_artifact_format: 'json',
          prompt_schema_version: 'sineforge.local-planning-prompt/v1',
          target_duration_sec: Number(data.story.target_duration_sec || packageData?.duration_analysis.target_duration_sec || 300),
          audience: data.story.audience ?? null,
          genre: data.story.genre ?? null,
          tone: data.story.tone ?? null,
          language: 'English',
          visual_style: data.story.visual_style ?? null,
          requested_by: `CineForge UI reviewer: ${label}`,
        })
        setPipeline(result.pipeline)
        const versions = await loadPhaseHistory(1)
        const latest = versions.at(-1)
        setSelectedByPhase((current) => ({
          ...current,
          1: latest?.id,
        }))
        setLoadedDetail(null)
        setApprovalNotice(result.completion_message)
        setIterationLabel('')
        setIterationNotes('')
        setCreateOpen(false)
        return
      }
      if (planningPhaseRegenerateIteration) {
        const result = await api.generatePlanningPhaseIteration(
          storyId,
          selectedPhaseNumber,
          {
            idempotency_key: iterationIdempotencyKey.current,
            label,
            notes: iterationNotes,
            requested_by: 'CineForge UI reviewer',
          },
        )
        setPipeline(result.pipeline)
        await loadPhaseHistory(selectedPhaseNumber)
        setSelectedByPhase((current) => ({
          ...current,
          [selectedPhaseNumber]: result.version.id,
        }))
        setLoadedDetail(result.version)
        setApprovalNotice(result.message)
        setIterationLabel('')
        setIterationNotes('')
        setCreateOpen(false)
        return
      }
      const created = await api.createPhaseVersion(storyId, selectedPhaseNumber, {
        label,
        notes: iterationNotes,
        requested_by: 'CineForge UI reviewer',
      })
      setPipeline(created.pipeline)
      setVersionsByPhase((current) => ({
        ...current,
        [selectedPhaseNumber]: [
          ...(current[selectedPhaseNumber] ?? []).filter((item) => item.id !== created.version.id),
          {
            id: created.version.id,
            version_number: created.version.version_number,
            label: created.version.label ?? label,
            notes: created.version.notes ?? '',
            source: created.version.source ?? 'manual',
            lifecycle_state: created.version.lifecycle_state,
            completed: created.version.completed,
            snapshot_schema_version: created.version.snapshot_schema_version ?? 1,
            input_hash: created.version.input_hash,
            output_hash: created.version.output_hash,
            created_by: created.version.created_by,
            previous_version_id: created.version.previous_version_id,
            created_at: created.version.created_at,
            updated_at: created.version.updated_at,
          },
        ].sort((a, b) => a.version_number - b.version_number),
      }))
      setSelectedByPhase((current) => ({
        ...current,
        [selectedPhaseNumber]: created.version.id,
      }))
      setLoadedDetail(created.version)
      setIterationLabel('')
      setIterationNotes('')
      setCreateOpen(false)
    } catch (caught) {
      setHistoryError(
        caught instanceof Error ? caught.message : 'Unable to retain the current draft iteration.',
      )
    } finally {
      setSavingIteration(false)
      setWorkingPhaseNumber(null)
    }
  }

  const loadWorkflowTemplates = async () => {
    setWorkflowLoading(true)
    setWorkflowError(null)
    try {
      const templates = await api.listRuntimeWorkflowTemplates()
      setWorkflowTemplates(templates ?? [])
    } catch (caught) {
      setWorkflowError(
        caught instanceof Error ? caught.message : 'Unable to load runtime workflow templates.',
      )
    } finally {
      setWorkflowLoading(false)
    }
  }

  const openPhaseFiveWorkflowPicker = async () => {
    setWorkflowOpen(true)
    setWorkflowError(null)
    setQueueProgress(null)
    await loadWorkflowTemplates()
  }

  const approveSelectedPhase = async () => {
    if (!selectedPhase || historical) return
    if (selectedPhaseNumber === 5) {
      await openPhaseFiveWorkflowPicker()
      return
    }
    if (selectedPhase.lifecycle_state === 'approved') return
    setApprovingPhase(true)
    setWorkingPhaseNumber(selectedPhaseNumber)
    setApprovalNotice(null)
    setError(null)
    try {
      const result = await api.approveProductionPhase(storyId, selectedPhaseNumber, {
        approved_by: 'CineForge QA',
        notes: `QA approved the Phase ${selectedPhaseNumber} planning snapshot. No media generation or execution was certified or started.`,
      })
      setPipeline(result.pipeline)
      setApprovalNotice(result.message)
      await loadPhaseHistory(selectedPhaseNumber)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Unable to approve Phase ${selectedPhaseNumber}.`)
    } finally {
      setApprovingPhase(false)
      setWorkingPhaseNumber(null)
    }
  }

  const handleWorkflowUpload = async (file: File | null) => {
    setWorkflowError(null)
    setWorkflowUploadJson(null)
    setWorkflowUploadName('')
    if (!file) return
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as unknown
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Workflow JSON must be a ComfyUI API object.')
      }
      setWorkflowUploadJson(parsed as Record<string, unknown>)
      setWorkflowUploadName(file.name)
    } catch (caught) {
      setWorkflowError(
        caught instanceof Error ? caught.message : 'Unable to read the uploaded workflow JSON.',
      )
    }
  }

  const phaseFiveWorkflowPayload = (): Pick<
    StartingImageGenerateRequest,
    'workflow_template_id' | 'workflow_label' | 'workflow_source' | 'workflow_api_json'
  > => {
    if (workflowUploadJson) {
      return {
        workflow_template_id: null,
        workflow_label: workflowUploadName || 'Uploaded ComfyUI API workflow',
        workflow_source: 'uploaded_api_json',
        workflow_api_json: workflowUploadJson,
      }
    }
    const selected = workflowTemplates.find((template) => template.id === workflowSelection)
    if (selected) {
      return {
        workflow_template_id: selected.id,
        workflow_label: `${selected.name} v${selected.version}`,
        workflow_source: 'runtime_catalog_template',
        workflow_api_json: null,
      }
    }
    return {
      workflow_template_id: null,
      workflow_label: 'Configured Flux2 API spine',
      workflow_source: 'configured_phase6_flux2_api_spine',
      workflow_api_json: null,
    }
  }

  const approvePhaseFiveAndQueueImages = async () => {
    if (!selectedPhase || historical) return
    setApprovingPhase(true)
    setWorkingPhaseNumber(5)
    setWorkflowError(null)
    setApprovalNotice(null)
    setError(null)
    try {
      if (selectedPhase.lifecycle_state !== 'approved') {
        const result = await api.approveProductionPhase(storyId, 5, {
          approved_by: 'CineForge QA',
          notes: 'QA approved the Phase 5 prompt and workflow package. Workflow selection follows for Phase 6 local image generation.',
        })
        setPipeline(result.pipeline)
        await loadPhaseHistory(5)
      }
      const workflowPayload = phaseFiveWorkflowPayload()
      const rows = data?.chapters.flatMap((chapter) =>
        chapter.scenes.flatMap((scene) =>
          scene.shots.map((shot) => ({ chapter, scene, shot })),
        ),
      ) ?? []
      const characterCount = data?.characters.length ?? 0
      const estimatedAssetTargets = new Set(
        rows
          .map((row) => row.shot.location || row.scene.title)
          .filter((value): value is string => Boolean(value)),
      ).size || (rows.length ? 1 : 0)
      setQueueProgress({
        completed: 0,
        total: characterCount + estimatedAssetTargets + rows.length,
        message: 'Submitting Phase 5 handoff: characters → reusable assets → scene starting images.',
      })
      const handoff = await api.generatePhaseFiveHandoff(storyId, {
        requested_by: 'CineForge Phase 5 workflow handoff',
        model_name: 'flux2_dev_fp8mixed.safetensors',
        ...workflowPayload,
      })
      const completedTotal = handoff.character_count + handoff.asset_count + handoff.scene_count
      setQueueProgress({
        completed: completedTotal,
        total: completedTotal,
        message: handoff.message,
      })
      setApprovalNotice(
        `Phase 5 workflow handoff complete: ${handoff.character_count} character reference${handoff.character_count === 1 ? '' : 's'}, ${handoff.asset_count} reusable asset reference${handoff.asset_count === 1 ? '' : 's'}, and ${handoff.scene_count} scene starting image${handoff.scene_count === 1 ? '' : 's'} generated with attachment labels.`,
      )
      setWorkflowOpen(false)
      await load()
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Unable to approve Phase 5 and submit the image batch.'
      setWorkflowError(message)
      setError(message)
    } finally {
      setApprovingPhase(false)
      setWorkingPhaseNumber(null)
    }
  }

  const exportAll = async () => {
    try {
      const exported = await api.exportPhaseHistory(storyId)
      downloadText(
        `story-${storyId}-phase-history.cineforge.json`,
        JSON.stringify(exported, null, 2),
      )
    } catch (caught) {
      setHistoryError(
        caught instanceof Error ? caught.message : 'Complete history export failed integrity checks.',
      )
    }
  }

  const exportSelected = () => {
    if (!selectedIteration || !loadedDetail) return
    downloadText(
      `story-${storyId}-phase-${selectedPhaseNumber}-v${selectedIteration.version_number}.json`,
      JSON.stringify(
        {
          schema: 'cineforge.phase-iteration',
          version: 1,
          iteration: selectedIteration,
          detail: loadedDetail,
        },
        null,
        2,
      ),
    )
  }

  if (loading) return <LoadingState title="Loading the eight-phase production contract…" />
  if (!pipeline) return error ? <ErrorNotice message={error} /> : null

  const currentSnapshotMetrics = snapshotMetricsFromWorkspace(currentWorkspace)
  const historicalMetrics = snapshotMetricsFromWorkspace(
    incompleteReason ? null : historicalWorkspace,
  )
  const packageDuration = packageData?.duration_analysis
  const packageEmotional = stringList(packageData?.emotional_progression)
  const packageAssumptions = stringList(packageData?.creative_assumptions)
  const packageDirection = packageData?.creative_direction ?? {}
  const phaseApprovalBlockedReason = historical
    ? 'Return to the current draft before approving.'
    : selectedPhase?.is_locked
      ? selectedPhase.locked_reason || `Phase ${selectedPhaseNumber} is locked.`
      : selectedPhaseNumber === 1 && !qa?.passed
        ? 'Phase 1 planning QA must pass before approval.'
        : null

  return (
    <section className="production-contract" aria-labelledby="production-contract-title">
      <div className="production-contract-heading">
        <div>
          <span className="eyebrow">EXACT EIGHT-PHASE PRODUCTION</span>
          <h2 id="production-contract-title">From one prompt to a controlled film production</h2>
          <p>
            All eight UI workspaces are available for review. Iteration history is stored in local SQLite
            via the production API—not browser IndexedDB. Design navigation never launches media generation or rendering.
          </p>
        </div>
        <span className="phase-count-pill">8 complete workspaces</span>
      </div>

      <div className="production-phase-rail" role="tablist" aria-label="Eight production phases">
        {pipeline.phases.map((phase, index) => {
          const count = phase.version_count
            ?? versionsByPhase[phase.phase_number]?.length
            ?? (phase.latest_version ? 1 : 0)
          return (
            <button
              key={phase.id}
              ref={(node) => { phaseTabs.current[index] = node }}
              id={`production-phase-tab-${phase.phase_number}`}
              type="button"
              role="tab"
              aria-label={`${phase.phase_number}. ${phase.name}. ${count} retained iteration${count === 1 ? '' : 's'}.`}
              aria-selected={selectedPhaseNumber === phase.phase_number}
              aria-controls={`production-phase-panel-${phase.phase_number}`}
              tabIndex={selectedPhaseNumber === phase.phase_number ? 0 : -1}
              aria-busy={workingPhaseNumber === phase.phase_number ? 'true' : undefined}
              className={[
                selectedPhaseNumber === phase.phase_number ? 'current' : '',
                workingPhaseNumber === phase.phase_number ? 'working' : '',
              ].filter(Boolean).join(' ')}
              onClick={() => selectPhase(phase.phase_number)}
              onKeyDown={(event) => handlePhaseKeyDown(event, index)}
            >
              <span>{phase.lifecycle_state === 'approved' ? '✓' : phase.phase_number}</span>
              <div>
                <b>{phase.phase_number}. {phase.name}</b>
                <small>{stateLabel(phase.lifecycle_state)}</small>
              </div>
              <em className="phase-iteration-badge" aria-hidden="true" title={`${count} retained iterations`}>{count}</em>
            </button>
          )
        })}
      </div>

      <div className={`phase-iteration-bar${historical ? ' viewing-history' : ''}`} aria-label={`Phase ${selectedPhaseNumber} iteration history`}>
        <div className="phase-version-nav">
          <button type="button" onClick={() => moveVersion(-1)} disabled={versionIndex === 0} aria-label="Previous iteration">‹</button>
          <label>
            <span>PHASE {selectedPhaseNumber} ITERATION</span>
            <select
              value={selectedIterationId}
              onChange={(event) => {
                setSelectedByPhase((current) => ({
                  ...current,
                  [selectedPhaseNumber]: event.target.value || undefined,
                }))
                setCompare(false)
                setEditing(false)
              }}
            >
              <option value="">Current draft</option>
              {phaseHistory.map((iteration) => (
                <option key={iteration.id} value={iteration.id}>
                  v{iteration.version_number} · {iteration.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => moveVersion(1)} disabled={versionIndex === versionTimeline.length - 1} aria-label="Next iteration">›</button>
        </div>
        <div className="phase-version-status">
          <span>{versionIndex + 1} of {versionTimeline.length}</span>
          <b>
            {historyLoading
              ? 'Loading retained history…'
              : selectedIteration
                ? `Viewing v${selectedIteration.version_number} · ${selectedIteration.label}`
                : 'Current working draft'}
          </b>
          <small>
            {selectedIteration
              ? `${new Date(selectedIteration.created_at).toLocaleString()} · immutable SQLite snapshot · read-only`
              : `${phaseHistory.length} retained iteration${phaseHistory.length === 1 ? '' : 's'} · edits stay in the current draft`}
          </small>
        </div>
        <div className="phase-version-actions">
          <button type="button" onClick={() => setHistoryOpen(true)} aria-expanded={historyOpen}>History</button>
          {selectedIteration ? (
            <button type="button" aria-pressed={compare} className={compare ? 'active' : ''} onClick={() => setCompare((value) => !value)}>
              Compare
            </button>
          ) : null}
          <button type="button" className="primary" onClick={() => {
            iterationIdempotencyKey.current = `phase-iteration-${crypto.randomUUID()}`
            setCreateOpen(true)
          }}>
            {selectedIteration
              ? 'Retain current'
              : selectedPhaseNumber <= 5
                ? 'New iteration'
                : 'Retain current state'}
          </button>
        </div>
      </div>

      {error ? <ErrorNotice message={error} /> : null}
      {historyError ? <div className="phase-history-error" role="alert"><b>History error</b><p>{historyError}</p></div> : null}

      {selectedPhase ? (
        <section className="phase-approval-bar" aria-label={`Phase ${selectedPhaseNumber} planning approval`}>
          <div>
            <span className="eyebrow">PLANNING QA GATE</span>
            <b>
              {selectedPhase.lifecycle_state === 'approved'
                ? `Phase ${selectedPhaseNumber} planning snapshot approved`
                : `Phase ${selectedPhaseNumber} awaits QA approval`}
            </b>
            <p>
              {selectedPhaseNumber === 5
                ? 'Phase 5 approval opens workflow selection, then runs one local handoff batch: character references first, reusable asset references second, and scene starting images third. Scene images carry attachment labels for the characters and assets they use.'
                : 'Approval records review of this planning snapshot only. It does not certify or start image, voice, video, ComfyUI, queue, or FFmpeg execution.'}
            </p>
            {phaseApprovalBlockedReason ? <small>{phaseApprovalBlockedReason}</small> : null}
            {approvalNotice ? <small role="status">{approvalNotice}</small> : null}
            {queueProgress ? (
              <small role="status">
                {queueProgress.message} {queueProgress.total ? `(${queueProgress.completed}/${queueProgress.total})` : ''}
              </small>
            ) : null}
          </div>
          <button
            type="button"
            className="btn primary"
            disabled={
              approvingPhase
              || (selectedPhase.lifecycle_state === 'approved' && selectedPhaseNumber !== 5)
              || Boolean(phaseApprovalBlockedReason)
            }
            onClick={() => void approveSelectedPhase()}
          >
            {approvingPhase && selectedPhaseNumber === 5
              ? 'Submitting Phase 5 handoff…'
              : approvingPhase
                ? `Approving Phase ${selectedPhaseNumber}…`
                : selectedPhaseNumber === 5 && selectedPhase.lifecycle_state === 'approved'
                  ? 'Select workflow & queue images'
                  : selectedPhaseNumber === 5
                    ? 'Approve Phase 5 & choose workflow'
                    : selectedPhase.lifecycle_state === 'approved'
                      ? `Phase ${selectedPhaseNumber} planning approved`
                      : `Approve Phase ${selectedPhaseNumber} planning snapshot`}
          </button>
        </section>
      ) : null}

      {workflowOpen ? (
        <div className="phase-workflow-modal" role="dialog" aria-modal="true" aria-labelledby="phase-five-workflow-title">
          <section>
            <header>
              <div>
                <span className="eyebrow">PHASE 5 HANDOFF</span>
                <h3 id="phase-five-workflow-title">Choose image workflow</h3>
                <p>Approval will submit one ordered batch: characters, reusable assets, then scene images. Scene image metadata will include labels that attach the image to the character and asset references it consumed.</p>
              </div>
              <button type="button" aria-label="Close workflow selector" onClick={() => setWorkflowOpen(false)} disabled={approvingPhase}>
                ×
              </button>
            </header>
            {workflowError ? <div className="phase-history-error" role="alert"><b>Workflow error</b><p>{workflowError}</p></div> : null}
            <label>
              <span>Static workflow</span>
              <select
                value={workflowSelection}
                disabled={approvingPhase || workflowLoading || Boolean(workflowUploadJson)}
                onChange={(event) => setWorkflowSelection(event.target.value)}
              >
                <option value={DEFAULT_PHASE_FIVE_WORKFLOW}>Configured Flux2 API spine</option>
                {workflowTemplates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name} v{template.version}
                  </option>
                ))}
              </select>
              <small>{workflowLoading ? 'Loading templates…' : `${workflowTemplates.length} runtime template${workflowTemplates.length === 1 ? '' : 's'} available`}</small>
            </label>
            <label>
              <span>Upload API workflow</span>
              <input
                type="file"
                accept="application/json,.json"
                disabled={approvingPhase}
                onChange={(event) => void handleWorkflowUpload(event.currentTarget.files?.[0] ?? null)}
              />
              <small>{workflowUploadName || 'Optional ComfyUI API JSON; uploaded workflow overrides the static selection.'}</small>
            </label>
            {workflowUploadJson ? (
              <button
                type="button"
                className="secondary-button"
                disabled={approvingPhase}
                onClick={() => {
                  setWorkflowUploadJson(null)
                  setWorkflowUploadName('')
                }}
              >
                Clear uploaded workflow
              </button>
            ) : null}
            {queueProgress ? (
              <div className="phase-queue-progress" role="status">
                <span style={{ width: `${queueProgress.total ? Math.round((queueProgress.completed / queueProgress.total) * 100) : 0}%` }} />
                <b>{queueProgress.message}</b>
                <small>{queueProgress.completed}/{queueProgress.total}</small>
              </div>
            ) : null}
            <footer>
              <button type="button" className="secondary-button" disabled={approvingPhase} onClick={() => setWorkflowOpen(false)}>
                Cancel
              </button>
              <button type="button" className="primary-button" disabled={approvingPhase} onClick={() => void approvePhaseFiveAndQueueImages()}>
                {approvingPhase ? 'Submitting handoff batch…' : 'Approve and submit handoff batch'}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {historical && selectedIteration ? (
        <div className="phase-history-banner" role="status">
          <div>
            <b>Read-only retained iteration</b>
            <p>
              You are reviewing Phase {selectedPhaseNumber} v{selectedIteration.version_number}.
              This SQLite snapshot cannot be overwritten. Editor links open the current working draft only.
              Historical workspaces never substitute live aggregate data.
            </p>
            {selectedIteration.notes ? <small>{selectedIteration.notes}</small> : null}
          </div>
          <button
            type="button"
            onClick={() => setSelectedByPhase((current) => ({ ...current, [selectedPhaseNumber]: undefined }))}
          >
            Return to current
          </button>
        </div>
      ) : null}

      {compare && historical && selectedIteration ? (
        <section className="phase-comparison" aria-label="Iteration summary metric comparison">
          <header>
            <div>
              <span>SUMMARY METRICS</span>
              <b>Phase {selectedPhaseNumber} · v{selectedIteration.version_number} versus current draft</b>
            </div>
            <small>Counts never claim rendered production output.</small>
          </header>
          <div>
            {historicalMetrics.map((metric, index) => {
              const currentValue = currentSnapshotMetrics[index]?.value ?? 0
              const delta = currentValue - metric.value
              return (
                <article key={metric.label} className={delta ? 'changed' : 'same'}>
                  <span>{metric.label}</span>
                  <div>
                    <small>v{selectedIteration.version_number}</small>
                    <b>{metric.value}</b>
                    <i>→</i>
                    <small>Current</small>
                    <strong>{currentValue}</strong>
                  </div>
                  <em>{delta === 0 ? 'Same count' : `${delta > 0 ? '+' : ''}${delta}`}</em>
                </article>
              )
            })}
          </div>
        </section>
      ) : null}

      <span className="sr-only" aria-live="polite">
        {selectedIteration
          ? `Viewing phase ${selectedPhaseNumber}, iteration ${selectedIteration.version_number}`
          : `Viewing current phase ${selectedPhaseNumber} draft`}
      </span>

      <div
        id={`production-phase-panel-${selectedPhaseNumber}`}
        className="production-phase-panel"
        role="tabpanel"
        aria-labelledby={`production-phase-tab-${selectedPhaseNumber}`}
        tabIndex={0}
      >
        {historyLoading && selectedIterationId ? (
          <LoadingState title="Loading retained iteration…" />
        ) : selectedPhaseNumber === 1 ? (
          <>
            {historical && incompleteReason ? (
              <div className="phase-history-error phase-legacy-incomplete" role="alert">
                <div>
                  <b>Legacy snapshot is incomplete</b>
                  <p>{incompleteReason} The current draft was not substituted.</p>
                </div>
              </div>
            ) : !packageData && historical ? (
              <div className="phase-empty">
                <span aria-hidden="true">＋</span>
                <div>
                  <b>This retained snapshot has no Phase 1 script package</b>
                  <p>
                    Phase 1 baselines store narrative planning state rather than a generated script package.
                    The current draft was not substituted. Return to current draft to edit live records.
                  </p>
                </div>
              </div>
            ) : !packageData ? (
              <div className="phase-empty">
                <span aria-hidden="true">＋</span>
                <div>
                  <b>Phase 1 has not started</b>
                  <p>Add an original creative prompt and target duration to create the first script package.</p>
                </div>
              </div>
            ) : (
              <div className="phase-workspace phase-one-workspace">
                <div className="phase-workspace-header">
                  <div>
                    <span className="eyebrow">
                      PHASE 1 · {historical ? 'RETAINED SNAPSHOT' : 'PROTOTYPE DATA'}
                    </span>
                    <h3>Script and Narrative Development</h3>
                    <p>
                      Review the narrative foundation, duration intent, source fidelity, and planning boundary before segmentation begins.
                    </p>
                  </div>
                  <div className="phase-workspace-meta">
                    <span className="phase-workspace-meta-pill">
                      {historical ? 'Read-only history' : 'Design available'}
                    </span>
                    <small>
                      {historical
                        ? `v${selectedIteration?.version_number ?? '—'} · immutable`
                        : `Backend state · ${stateLabel(phaseOne?.lifecycle_state || 'drafting')}`}
                    </small>
                    <div className="phase-header-actions" aria-label="Related workspaces">
                      {!editing && !historical ? (
                        <button type="button" className="btn secondary" onClick={beginEdit}>
                          Edit script package
                        </button>
                      ) : null}
                      {onNavigate ? (
                        <>
                          <button type="button" className="btn secondary" onClick={() => onNavigate('story')}>
                            Open for UI/UX review
                          </button>
                          <button type="button" className="btn secondary" onClick={() => onNavigate('story')}>
                            Open story editor <span aria-hidden="true">↗</span>
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="phase-preview-disclosure" role="note">
                  <span aria-hidden="true">◇</span>
                  <div>
                    <b>{historical ? 'Immutable retained snapshot' : 'Interactive UI/UX prototype'}</b>
                    <p>
                      {historical
                        ? 'This workspace renders only the verified SQLite snapshot for the selected iteration. It never substitutes current draft records.'
                        : 'This workspace reads current planning records for display. It does not generate media, submit jobs, call ComfyUI, synthesize voices, run FFmpeg, or change execution gates.'}
                    </p>
                  </div>
                </div>

                {(() => {
                  const targetSec = Number(packageDuration?.target_duration_sec || 0)
                  const plannedSec = Number(packageDuration?.estimated_total_duration_sec || 0)
                  const narrationWords = Number(packageDuration?.narration_word_count || 0)
                  const failCount = Array.isArray(qa?.checks)
                    ? qa.checks.filter((check) => !check.passed).length
                    : 0
                  const readinessPct = qa
                    ? Math.round(
                        ((qa.checks?.filter((check) => check.passed).length || 0)
                          / Math.max(1, qa.checks?.length || 1))
                          * 100,
                      )
                    : historical
                      ? 100
                      : 0
                  const qaLabel = historical
                    ? 'Historical'
                    : qa?.passed
                      ? 'Passed'
                      : qa
                        ? 'Needs review'
                        : '—'
                  return (
                    <div className="phase-metrics six" aria-label="Phase 1 script metrics">
                      <article className="phase-metric">
                        <span>Script words</span>
                        <strong>{Number(packageData.script_word_count || 0).toLocaleString()}</strong>
                      </article>
                      <article className="phase-metric">
                        <span>Narration words</span>
                        <strong>{narrationWords.toLocaleString()}</strong>
                      </article>
                      <article className="phase-metric">
                        <span>Target runtime</span>
                        <strong>{targetSec ? formatDuration(targetSec) : '—'}</strong>
                        {packageData.planned_scene_count ? (
                          <small>
                            {packageData.planned_scene_count} scenes · 8s nominal · 6–10s clips
                          </small>
                        ) : null}
                      </article>
                      <article className="phase-metric">
                        <span>Planned runtime</span>
                        <strong>{plannedSec ? formatDuration(plannedSec) : '—'}</strong>
                      </article>
                      <article className="phase-metric">
                        <span>Readiness</span>
                        <strong>{readinessPct}%</strong>
                      </article>
                      <article className="phase-metric">
                        <span>Planning QA</span>
                        <strong className={qa?.passed || historical ? 'qa-pass' : 'qa-fail'}>
                          {qaLabel}
                        </strong>
                        {!historical && failCount > 0 ? (
                          <small>{failCount} open gate{failCount === 1 ? '' : 's'}</small>
                        ) : null}
                      </article>
                    </div>
                  )
                })()}

                {editing && draft && !historical ? (
                  <div className="phase-one-editor panel">
                    <label>Project title<input value={draft.project_title} onChange={(event) => setDraft({ ...draft, project_title: event.target.value })} /></label>
                    <label>Logline<textarea value={draft.logline} onChange={(event) => setDraft({ ...draft, logline: event.target.value })} /></label>
                    <label>Short synopsis<textarea value={draft.short_synopsis} onChange={(event) => setDraft({ ...draft, short_synopsis: event.target.value })} /></label>
                    <label>Detailed treatment<textarea className="tall" value={draft.detailed_treatment} onChange={(event) => setDraft({ ...draft, detailed_treatment: event.target.value })} /></label>
                    <label>Complete script<textarea className="script" value={draft.complete_script} onChange={(event) => setDraft({ ...draft, complete_script: event.target.value })} /></label>
                    <label>Narration script<textarea className="tall" value={draft.narration_script} onChange={(event) => setDraft({ ...draft, narration_script: event.target.value })} /></label>
                    <label>Dialogue script<textarea value={draft.dialogue_script} onChange={(event) => setDraft({ ...draft, dialogue_script: event.target.value })} /></label>
                    <label>Non-dialogue action · one item per line<textarea value={listText(draft.non_dialogue_action)} onChange={(event) => setDraft({ ...draft, non_dialogue_action: textList(event.target.value) })} /></label>
                    <label>Silent visual beats · one item per line<textarea value={listText(draft.silent_visual_beats)} onChange={(event) => setDraft({ ...draft, silent_visual_beats: textList(event.target.value) })} /></label>
                    <label>Source-fidelity notes · one item per line<textarea value={listText(draft.source_fidelity_notes)} onChange={(event) => setDraft({ ...draft, source_fidelity_notes: textList(event.target.value) })} /></label>
                    <label>Creative assumptions · one item per line<textarea value={listText(draft.creative_assumptions)} onChange={(event) => setDraft({ ...draft, creative_assumptions: textList(event.target.value) })} /></label>
                    <div className="phase-one-editor-actions">
                      <button type="button" className="secondary-button" disabled={saving} onClick={() => { setEditing(false); setDraft(null) }}>Cancel</button>
                      <button type="button" className="primary-button" disabled={saving} onClick={() => void saveRevision()}>
                        {saving ? 'Saving version…' : 'Save as new version & rerun QA'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <section className="phase-document" aria-label="Phase 1 script document">
                    <div>
                      <span>WORKING TITLE</span>
                      <h4>{packageData.project_title}</h4>
                    </div>
                    <div>
                      <span>LOGLINE</span>
                      <p>{packageData.logline || 'No logline has been recorded.'}</p>
                    </div>
                    <div>
                      <span>SHORT SYNOPSIS</span>
                      <p>{packageData.short_synopsis || 'No synopsis has been recorded.'}</p>
                    </div>
                    <details open>
                      <summary>Source story and treatment</summary>
                      <p>{packageData.detailed_treatment || 'Add the original story, script, narration, or treatment in Story & Chapters.'}</p>
                    </details>
                    <div className="phase-document-grid phase-document-pair">
                      <article>
                        <span>CREATIVE DIRECTION</span>
                        <p>
                          {[
                            typeof packageDirection.language === 'string' ? packageDirection.language : null,
                            typeof packageDirection.genre === 'string' ? packageDirection.genre : null,
                            typeof packageDirection.tone === 'string' ? packageDirection.tone : null,
                            typeof packageDirection.visual_style === 'string' ? packageDirection.visual_style : null,
                          ].filter(Boolean).join(' · ')
                            || packageEmotional.join(' · ')
                            || packageAssumptions.slice(0, 2).join(' · ')
                            || 'Planning text only.'}
                        </p>
                      </article>
                      <article>
                        <span>PRODUCTION BOUNDARY</span>
                        <p>
                          Planning text only. No scene media, voices, videos, render jobs, or final outputs are created here.
                        </p>
                      </article>
                    </div>
                  </section>
                )}

                <div className="phase-footer phase-one-review-footer">
                  <div>
                    <span className="eyebrow">PHASE 1 REVIEW</span>
                    <b>
                      {historical
                        ? 'Historical snapshot is read-only'
                        : qa?.passed
                          ? 'Human review remains required'
                          : 'Revision required before review'}
                    </b>
                    <p>
                      {historical
                        ? 'Return to the current draft to edit. This snapshot cannot be overwritten.'
                        : 'This workspace does not approve or execute production. Edit the script package to create a new immutable version.'}
                    </p>
                  </div>
                  {!historical ? (
                    <button type="button" className="btn primary" onClick={beginEdit}>
                      Edit story foundation
                    </button>
                  ) : null}
                </div>

                {!historical && qa ? (
                  <details className="phase-one-evidence-drawer">
                    <summary>
                      <span>PHASE 1 QA EVIDENCE</span>
                      <b>{qa.passed ? 'All blocking checks passed' : 'Open gates remain'}</b>
                      <small>Expand for QA checks and fail-closed boundary</small>
                    </summary>
                    <div className="split-2 phase-one-evidence">
                      <div className="panel">
                        <div className="panel-title">
                          <div>
                            <span className="eyebrow">PHASE 1 QA REPORT</span>
                            <h2>{qa.passed ? 'All blocking checks passed' : 'Revision required'}</h2>
                            <p>QA completion does not approve the script.</p>
                          </div>
                          <span className={`truth-pill ${qa.passed ? 'verified' : 'unknown'}`}>{qa.passed ? 'PASS' : 'FAIL'}</span>
                        </div>
                        <ul className="phase-qa-checks">
                          {qa.checks.map((check) => (
                            <li key={check.code} className={check.passed ? 'passed' : 'failed'}>
                              <span>{check.passed ? '✓' : '!'}</span>
                              <div><b>{check.label}</b><p>{check.detail}</p></div>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="panel">
                        <div className="panel-title">
                          <div>
                            <span className="eyebrow">FAIL-CLOSED BOUNDARY</span>
                            <h2>Nothing downstream executed</h2>
                            <p>These values are persisted in the QA evidence, not inferred by the UI.</p>
                          </div>
                        </div>
                        <ul className="phase-boundary-list">
                          {Object.entries(qa.phase_boundary ?? {}).map(([key, value]) => (
                            <li key={key}><span>{key.replaceAll('_', ' ')}</span><b>{value ? 'Yes' : 'No'}</b></li>
                          ))}
                        </ul>
                        {packageData.baseline_comparison ? (
                          <div className="baseline-result">
                            <span>TRANSFIGURATION BASELINE</span>
                            <b>{stateLabel(packageData.baseline_comparison.classification)}</b>
                            <p>{packageData.baseline_comparison.note}</p>
                            <small>
                              {packageData.baseline_comparison.missing_count} missing · {packageData.baseline_comparison.unsafe_count} unsafe · human review still required
                            </small>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </details>
                ) : null}
              </div>
            )}
          </>
        ) : displayPhase ? (
          <ProductionPhasePreview
            phase={displayPhase}
            workspace={historical ? (incompleteReason ? null : historicalWorkspace) : currentWorkspace}
            historical={historical}
            incompleteReason={historical ? incompleteReason : null}
            productionProfileKey={productionSettings?.production_profile_key}
            stitchStage={productionSettings?.stitch_stage}
            onNavigate={onNavigate}
          />
        ) : null}
      </div>

      {createOpen ? (
        <div className="phase-modal-backdrop" role="presentation" onClick={() => !savingIteration && setCreateOpen(false)}>
          <div
            className="phase-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="retain-iteration-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <h3 id="retain-iteration-title">
                {generateIteration ? 'Generate' : 'Retain'} Phase {selectedPhaseNumber} iteration
              </h3>
              <button type="button" aria-label="Close" disabled={savingIteration} onClick={() => setCreateOpen(false)}>×</button>
            </header>
            <div className="phase-iteration-form">
              <p>
                {phaseOneRegenerateIteration
                  ? 'This reruns Sulphur for Phase 1 using the current story prompt, then stores the generated package in SQLite history. Existing iterations are never changed.'
                  : planningPhaseRegenerateIteration
                    ? `This runs the selected local planning agent for Phase ${selectedPhaseNumber}, applies the validated phase-scoped proposal, and stores a new generated SQLite iteration. Existing iterations are never changed.`
                  : 'This captures the complete current draft from SQLite-backed backend records—not the visible historical copy. Existing iterations are never changed.'}
              </p>
              <label>
                Iteration name
                <input
                  autoFocus
                  value={iterationLabel}
                  onChange={(event) => setIterationLabel(event.target.value)}
                  placeholder={`Iteration ${phaseHistory.length + 1} · e.g. Director review`}
                />
              </label>
              <label>
                Notes <small>optional</small>
                <textarea
                  value={iterationNotes}
                  onChange={(event) => setIterationNotes(event.target.value)}
                  placeholder="What changed, what should be reviewed, or why this milestone matters."
                />
              </label>
              <div className="phase-iteration-form-meta">
                <span><b>Phase</b>{selectedPhaseNumber}. {selectedPhase?.name}</span>
                <span><b>Storage</b>SQLite production_phase_versions</span>
                <span><b>Shortcut</b>Ctrl/⌘ + Shift + S</span>
              </div>
              <div className="modal-actions">
                <button type="button" className="secondary-button" disabled={savingIteration} onClick={() => setCreateOpen(false)}>Cancel</button>
                <button type="button" className="primary-button" disabled={savingIteration} onClick={() => void saveIteration()}>
                  {savingIteration
                    ? (generateIteration ? 'Generating…' : 'Retaining…')
                    : (generateIteration ? 'Generate new iteration' : 'Retain current draft')}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {historyOpen ? (
        <div className="phase-modal-backdrop" role="presentation" onClick={() => setHistoryOpen(false)}>
          <div
            className="phase-modal wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="history-drawer-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <h3 id="history-drawer-title">Phase {selectedPhaseNumber} iteration history</h3>
              <button type="button" aria-label="Close" onClick={() => setHistoryOpen(false)}>×</button>
            </header>
            <div className="phase-history-drawer">
              <header>
                <div>
                  <span className="eyebrow">APPEND-ONLY SQLITE HISTORY</span>
                  <h4>{phaseHistory.length} retained iteration{phaseHistory.length === 1 ? '' : 's'}</h4>
                  <p>Browse, compare summary metrics, or export. Clearing browser site data does not delete these rows.</p>
                </div>
                <button type="button" className="secondary-button" onClick={() => void exportAll()}>Export all history</button>
              </header>
              <div className="phase-history-list">
                {phaseHistory.map((iteration) => (
                  <button
                    key={iteration.id}
                    type="button"
                    aria-current={selectedIterationId === iteration.id ? 'true' : undefined}
                    className={selectedIterationId === iteration.id ? 'active' : ''}
                    onClick={() => {
                      setSelectedByPhase((current) => ({
                        ...current,
                        [selectedPhaseNumber]: iteration.id,
                      }))
                      setHistoryOpen(false)
                      setCompare(false)
                    }}
                  >
                    <span>v{iteration.version_number}</span>
                    <div>
                      <b>{iteration.label}</b>
                      <p>{iteration.notes || 'No notes recorded for this iteration.'}</p>
                      <small>
                        {new Date(iteration.created_at).toLocaleString()} · {iteration.source === 'baseline' ? 'Initial baseline' : iteration.source}
                      </small>
                    </div>
                  </button>
                ))}
              </div>
              {selectedIteration && loadedDetail ? (
                <footer>
                  <div>
                    <b>Selected: v{selectedIteration.version_number} · {selectedIteration.label}</b>
                    <small>Output hash {selectedIteration.output_hash.slice(0, 12)}…</small>
                  </div>
                  <button type="button" className="secondary-button" onClick={exportSelected}>Download selected JSON</button>
                </footer>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
