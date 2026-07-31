import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react'

import {
  api,
  nativeApiRunnerOutputUrl,
  nativeApiRunnerWorkflowOpenUrl,
  type ApiCallerEditableField,
  type ApiCallerWorkflowNode,
  type NativeApiRunnerAnalysis,
  type NativeApiRunnerJob,
  type NativeApiRunnerRuntime,
  type NativeApiRunnerWorkflowDetail,
  type NativeApiRunnerWorkflowSummary,
} from '../../api/client'
import { formatDate } from '../../components/formatDate'
import {
  APP_NAVIGATION_REQUEST_EVENT,
  type AppNavigationRequestDetail,
} from '../../navigationGuard'
import { EmptyState, ErrorState, LoadingState } from '../components/StateBlocks'
import './ApiRunnerPage.css'

type WorkflowGraph = Record<string, ApiCallerWorkflowNode>
type EditorMode = 'inputs' | 'json'
type ConfirmAction =
  | { kind: 'remove' }
  | { kind: 'free-memory' }
  | null
type PendingReplacement =
  | { kind: 'workflow'; workflowId: string }
  | { kind: 'file'; file: File }
  | { kind: 'paste' }
  | null

type RunnerActivity = NativeApiRunnerJob & {
  workflowName: string
  submittedAt: string
  unknownPolls?: number
  pollingStopped?: boolean
}

type DraftSnapshot = {
  workflow: string
  name: string
  version: string
  description: string
  category: string
  subcategory: string
  episode: string
  instructions: string
  tags: string
  sourceFilename: string | null
  rawJson: string
  rawDirty: boolean
}

const TERMINAL_JOB_STATES = new Set<NativeApiRunnerJob['state']>([
  'completed',
  'failed',
])
const UNKNOWN_JOB_POLL_LIMIT = 8

function cloneGraph(workflow: WorkflowGraph): WorkflowGraph {
  return JSON.parse(JSON.stringify(workflow)) as WorkflowGraph
}

function unwrapGraph(value: unknown): WorkflowGraph {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Workflow JSON must be an object.')
  }
  const object = value as Record<string, unknown>
  let candidate: unknown = object
  if (object.prompt && typeof object.prompt === 'object' && !Array.isArray(object.prompt)) {
    candidate = object.prompt
  } else if (
    object.workflow &&
    typeof object.workflow === 'object' &&
    !Array.isArray(object.workflow) &&
    !Object.values(object).some(
      (node) =>
        node &&
        typeof node === 'object' &&
        !Array.isArray(node) &&
        'class_type' in node,
    )
  ) {
    candidate = object.workflow
  }
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
    throw new Error('Workflow JSON must contain an API-format prompt graph.')
  }
  const graph = candidate as Record<string, unknown>
  if (Array.isArray(graph.nodes) || Array.isArray(graph.links)) {
    throw new Error(
      'Visual workflow JSON is not executable here. Export with ComfyUI “Save (API Format)”.',
    )
  }
  if (!Object.keys(graph).length) {
    throw new Error('Workflow JSON must contain at least one node.')
  }
  for (const [nodeId, rawNode] of Object.entries(graph)) {
    if (!rawNode || typeof rawNode !== 'object' || Array.isArray(rawNode)) {
      throw new Error(`Node ${nodeId} must be an object.`)
    }
    const node = rawNode as Record<string, unknown>
    if (typeof node.class_type !== 'string' || !node.class_type.trim()) {
      throw new Error(
        `Node ${nodeId} has no class_type. Export with ComfyUI “Save (API Format)”.`,
      )
    }
    if (!node.inputs || typeof node.inputs !== 'object' || Array.isArray(node.inputs)) {
      throw new Error(`Node ${nodeId} has no inputs object.`)
    }
  }
  return graph as WorkflowGraph
}

function editableWorkflowFields(workflow: WorkflowGraph): ApiCallerEditableField[] {
  const result: ApiCallerEditableField[] = []
  for (const [nodeId, node] of Object.entries(workflow)) {
    const title =
      typeof node._meta?.title === 'string' && node._meta.title.trim()
        ? node._meta.title
        : node.class_type
    for (const [input, value] of Object.entries(node.inputs ?? {})) {
      if (!['string', 'number', 'boolean'].includes(typeof value)) continue
      const valueType =
        typeof value === 'boolean'
          ? 'bool'
          : typeof value === 'number'
            ? Number.isInteger(value)
              ? 'int'
              : 'float'
            : 'str'
      result.push({
        nodeId,
        classType: node.class_type,
        title,
        input,
        value: value as string | number | boolean,
        valueType,
        label: `${nodeId} | ${title} | ${input}`,
      })
    }
  }
  return result
}

function isLongField(field: ApiCallerEditableField): boolean {
  const key = `${field.input} ${field.title} ${field.classType}`.toLowerCase()
  return (
    String(field.value).length > 120 ||
    key.includes('prompt') ||
    key.includes('positive') ||
    key.includes('negative') ||
    key.includes('text')
  )
}

function fileStem(filename: string): string {
  return (
    filename
      .replace(/\.(api\.)?json$/i, '')
      .replace(/[_-]+/g, ' ')
      .trim() || 'Imported workflow'
  )
}

function graphSnapshot(workflow: WorkflowGraph): string {
  return JSON.stringify(workflow)
}

function activityStateLabel(state: NativeApiRunnerJob['state']): string {
  if (state === 'completed') return 'Complete'
  if (state === 'failed') return 'Failed'
  if (state === 'running') return 'Running'
  if (state === 'pending') return 'Queued'
  return 'Unknown'
}

function outputKind(filename: string): 'image' | 'video' | 'audio' | 'file' {
  const extension = filename.split('.').pop()?.toLowerCase()
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'].includes(extension ?? '')) return 'image'
  if (['mp4', 'webm', 'mov', 'mkv', 'avi'].includes(extension ?? '')) return 'video'
  if (['wav', 'mp3', 'flac', 'ogg', 'm4a'].includes(extension ?? '')) return 'audio'
  return 'file'
}

function makeIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `sineforge-native-${crypto.randomUUID()}`
  }
  return `sineforge-native-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function RunnerEmptyState({
  hasSavedWorkflows,
  onAdd,
  onPaste,
  onDrop,
}: {
  hasSavedWorkflows: boolean
  onAdd: () => void
  onPaste: () => void
  onDrop: (event: DragEvent<HTMLDivElement>) => void
}) {
  return (
    <section
      className="native-runner-empty"
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <div className="native-runner-empty-orbit" aria-hidden="true">
        <span />
        <span />
        <i>{'{ }'}</i>
      </div>
      <span className="eyebrow">
        {hasSavedWorkflows ? 'SHARED WORKFLOW LIBRARY' : 'OPERATOR WORKFLOWS'}
      </span>
      <h2>{hasSavedWorkflows ? 'Select a workflow' : 'No workflows yet'}</h2>
      <p>
        {hasSavedWorkflows
            ? 'Choose a saved workflow from the library, or load another ComfyUI API-format JSON working copy.'
            : (
              <>
                Load a ComfyUI API-format <code>.json</code> file or paste JSON to begin.
                Repository workflows and operator-created entries share this library.
              </>
            )}
      </p>
      <div>
        <button type="button" className="btn primary" onClick={onAdd}>
          ＋ Load API JSON
        </button>
        <button type="button" className="btn secondary" onClick={onPaste}>
          Paste JSON
        </button>
      </div>
      <small>Drop a .json file here · nothing is queued until you validate and run</small>
    </section>
  )
}

function RuntimeStrip({
  runtime,
  refreshing,
  onRefresh,
  onFreeMemory,
}: {
  runtime: NativeApiRunnerRuntime | null
  refreshing: boolean
  onRefresh: () => void
  onFreeMemory: () => void
}) {
  const ready = Boolean(runtime?.ok)
  const hasQueuedPrompt = Boolean(
    runtime?.queue.runningCount || runtime?.queue.pendingCount,
  )
  return (
    <section className="native-runner-runtime" data-ready={ready}>
      <div className="native-runner-runtime-mark" aria-hidden="true">
        <span />
      </div>
      <div>
        <span>Native execution target</span>
        <b>{ready ? 'ComfyUI ready' : 'ComfyUI unavailable'}</b>
        <small>{runtime?.comfyUrl ?? 'http://127.0.0.1:8888'} · direct CineForge connection</small>
      </div>
      <dl>
        <div>
          <dt>Node classes</dt>
          <dd>{runtime?.objectInfo.classCount ?? '—'}</dd>
        </div>
        <div>
          <dt>Running</dt>
          <dd>{runtime?.queue.runningCount ?? '—'}</dd>
        </div>
        <div>
          <dt>Pending</dt>
          <dd>{runtime?.queue.pendingCount ?? '—'}</dd>
        </div>
      </dl>
      <span className="status-pill" data-status={ready ? 'ready' : 'blocked'}>
        {ready ? 'Direct · local' : 'Offline'}
      </span>
      <div className="native-runner-runtime-actions">
        <button type="button" className="btn quiet" disabled={refreshing} onClick={onRefresh}>
          {refreshing ? 'Checking…' : 'Refresh'}
        </button>
        <button
          type="button"
          className="btn quiet"
          disabled={!ready || refreshing || hasQueuedPrompt}
          title={
            hasQueuedPrompt
              ? 'Free VRAM is available after the ComfyUI queue is empty'
              : undefined
          }
          onClick={onFreeMemory}
        >
          Free VRAM
        </button>
      </div>
    </section>
  )
}

export function ApiRunnerPage() {
  const workflowFileRef = useRef<HTMLInputElement>(null)
  const mediaFileRef = useRef<HTMLInputElement>(null)
  const runRequestRef = useRef<{ snapshot: string; idempotencyKey: string } | null>(null)
  const [workflows, setWorkflows] = useState<NativeApiRunnerWorkflowSummary[]>([])
  const [selected, setSelected] = useState<NativeApiRunnerWorkflowDetail | null>(null)
  const [working, setWorking] = useState<WorkflowGraph>({})
  const [name, setName] = useState('')
  const [version, setVersion] = useState('1.0')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('Uncategorized')
  const [subcategory, setSubcategory] = useState('General')
  const [episode, setEpisode] = useState('')
  const [instructions, setInstructions] = useState('')
  const [tags, setTags] = useState('')
  const [sourceFilename, setSourceFilename] = useState<string | null>(null)
  const [rawJson, setRawJson] = useState('')
  const [mode, setMode] = useState<EditorMode>('inputs')
  const [analysis, setAnalysis] = useState<NativeApiRunnerAnalysis | null>(null)
  const [validatedSnapshot, setValidatedSnapshot] = useState('')
  const [runtime, setRuntime] = useState<NativeApiRunnerRuntime | null>(null)
  const [activities, setActivities] = useState<RunnerActivity[]>([])
  const [libraryFilter, setLibraryFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('All categories')
  const [fieldFilter, setFieldFilter] = useState('')
  const [dirty, setDirty] = useState(false)
  const [rawDirty, setRawDirty] = useState(false)
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteJson, setPasteJson] = useState('')
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [pendingReplacement, setPendingReplacement] = useState<PendingReplacement>(null)
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null)
  const [mediaFile, setMediaFile] = useState<File | null>(null)
  const [mediaTargetKey, setMediaTargetKey] = useState('')
  const [logs, setLogs] = useState<string[]>([
    'Native Runner initialized. External ComfyAPI Runner is not used.',
  ])
  const draftRef = useRef<DraftSnapshot>({
    workflow: graphSnapshot(working),
    name,
    version,
    description,
    category,
    subcategory,
    episode,
    instructions,
    tags,
    sourceFilename,
    rawJson,
    rawDirty,
  })

  useEffect(() => {
    draftRef.current = {
      workflow: graphSnapshot(working),
      name,
      version,
      description,
      category,
      subcategory,
      episode,
      instructions,
      tags,
      sourceFilename,
      rawJson,
      rawDirty,
    }
  }, [
    description,
    category,
    subcategory,
    episode,
    instructions,
    tags,
    name,
    rawDirty,
    rawJson,
    sourceFilename,
    version,
    working,
  ])

  const appendLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    setLogs((current) => [`${timestamp} · ${message}`, ...current].slice(0, 80))
  }, [])

  const refreshRuntime = useCallback(async (quiet = false) => {
    if (!quiet) {
      setAction('refreshing-runtime')
      setError(null)
    }
    try {
      const result = await api.getNativeApiRunnerRuntime()
      setRuntime(result)
      if (!quiet) {
        setError(null)
        setNotice(result.ok ? 'ComfyUI runtime refreshed.' : 'ComfyUI is not ready.')
      }
    } catch (caught) {
      setRuntime(null)
      if (!quiet) {
        setError(caught instanceof Error ? caught.message : 'Unable to inspect ComfyUI.')
      }
    } finally {
      if (!quiet) setAction('')
    }
  }, [])

  const refreshLibrary = useCallback(async () => {
    const items = await api.listNativeApiRunnerWorkflows()
    setWorkflows(items)
    return items
  }, [])

  const refreshLibraryFromUi = useCallback(async () => {
    setAction('refreshing-library')
    setError(null)
    try {
      await refreshLibrary()
      setNotice('Native workflow library refreshed.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to refresh the library.')
    } finally {
      setAction('')
    }
  }, [refreshLibrary])

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [items, runtimeResult] = await Promise.all([
        api.listNativeApiRunnerWorkflows(),
        api.getNativeApiRunnerRuntime().catch(() => null),
      ])
      setWorkflows(items)
      setRuntime(runtimeResult)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the native API Runner.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadInitial(), 0)
    return () => window.clearTimeout(timer)
  }, [loadInitial])

  useEffect(() => {
    const timer = window.setInterval(() => void refreshRuntime(true), 10_000)
    return () => window.clearInterval(timer)
  }, [refreshRuntime])

  useEffect(() => {
    if (!dirty && !rawDirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, rawDirty])

  const modalKind = pasteOpen
    ? 'paste'
    : pendingReplacement || pendingNavigation
      ? 'discard'
      : confirmAction?.kind ?? null
  useEffect(() => {
    if (!modalKind) return
    const previous = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    const modal = document.querySelector<HTMLElement>('.native-runner-modal')
    const focusableSelector =
      'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const frame = window.requestAnimationFrame(() => {
      const preferred = modal?.querySelector<HTMLElement>('[autofocus]')
      const first = modal?.querySelector<HTMLElement>(focusableSelector)
      const focusTarget = preferred ?? first
      focusTarget?.focus()
    })
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPasteOpen(false)
        setPasteJson('')
        setPendingReplacement(null)
        setPendingNavigation(null)
        setConfirmAction(null)
        return
      }
      if (event.key !== 'Tab' || !modal) return
      const focusable = [...modal.querySelectorAll<HTMLElement>(focusableSelector)]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('keydown', handleKeyDown)
      if (previous?.isConnected) previous.focus()
    }
  }, [modalKind])

  useEffect(() => {
    if (!dirty && !rawDirty) return
    const guardNavigation = (event: Event) => {
      const request = event as CustomEvent<AppNavigationRequestDetail>
      if (typeof request.detail?.proceed !== 'function') return
      event.preventDefault()
      setPendingNavigation(() => request.detail.proceed)
    }
    window.addEventListener(APP_NAVIGATION_REQUEST_EVENT, guardNavigation)
    return () => window.removeEventListener(APP_NAVIGATION_REQUEST_EVENT, guardNavigation)
  }, [dirty, rawDirty])

  const activeJobKey = useMemo(
    () =>
      activities
        .filter(
          (job) => !TERMINAL_JOB_STATES.has(job.state) && !job.pollingStopped,
        )
        .map((job) => job.promptId)
        .sort()
        .join('|'),
    [activities],
  )

  useEffect(() => {
    if (!activeJobKey) return
    let active = true
    let timer = 0
    const promptIds = activeJobKey.split('|')
    const unknownAttempts = new Map(promptIds.map((promptId) => [promptId, 0]))
    const poll = async () => {
      try {
        const results = await Promise.all(
          promptIds.map((promptId) => api.getNativeApiRunnerJob(promptId)),
        )
        if (!active) return
        const validResults = results.filter(
          (result): result is NativeApiRunnerJob => Boolean(result?.promptId),
        )
        for (const result of validResults) {
          unknownAttempts.set(
            result.promptId,
            result.state === 'unknown'
              ? (unknownAttempts.get(result.promptId) ?? 0) + 1
              : 0,
          )
        }
        setActivities((current) =>
          current.map((activity) => {
            const update = validResults.find((result) => result.promptId === activity.promptId)
            if (!update) return activity
            const unknownPolls = unknownAttempts.get(update.promptId) ?? 0
            return {
              ...activity,
              ...update,
              unknownPolls,
              pollingStopped:
                update.state === 'unknown' &&
                unknownPolls >= UNKNOWN_JOB_POLL_LIMIT,
            }
          }),
        )
        const stillActive = validResults.some(
          (result) =>
            !TERMINAL_JOB_STATES.has(result.state) &&
            !(
              result.state === 'unknown' &&
              (unknownAttempts.get(result.promptId) ?? 0) >= UNKNOWN_JOB_POLL_LIMIT
            ),
        )
        if (stillActive) {
          timer = window.setTimeout(() => void poll(), 2_000)
        }
      } catch {
        if (active) timer = window.setTimeout(() => void poll(), 4_000)
      }
    }
    void poll()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [activeJobKey])

  const localFields = useMemo(() => editableWorkflowFields(working), [working])
  const editableFields = analysis?.editable.length ? analysis.editable : localFields
  const visibleFields = useMemo(() => {
    const query = fieldFilter.trim().toLowerCase()
    if (!query) return editableFields
    return editableFields.filter((field) =>
      `${field.nodeId} ${field.classType} ${field.title} ${field.input} ${field.value}`
        .toLowerCase()
        .includes(query),
    )
  }, [editableFields, fieldFilter])
  const groupedFields = useMemo(() => {
    const groups = new Map<string, ApiCallerEditableField[]>()
    for (const field of visibleFields) {
      const values = groups.get(field.nodeId) ?? []
      values.push(field)
      groups.set(field.nodeId, values)
    }
    return [...groups.entries()]
  }, [visibleFields])
  const categoryOptions = useMemo(() => {
    const counts = new Map<string, number>()
    for (const workflow of workflows) {
      counts.set(workflow.category, (counts.get(workflow.category) ?? 0) + 1)
    }
    return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [workflows])
  const visibleWorkflows = useMemo(() => {
    const query = libraryFilter.trim().toLowerCase()
    return workflows.filter((workflow) =>
      (categoryFilter === 'All categories' || workflow.category === categoryFilter) &&
      (!query ||
        (
          `${workflow.name} ${workflow.description ?? ''} ${workflow.source_filename ?? ''} ` +
          `${workflow.category} ${workflow.subcategory} ${workflow.episode ?? ''} ` +
          `${workflow.instructions ?? ''} ${workflow.tags.join(' ')}`
        )
            .toLowerCase()
            .includes(query)),
    )
  }, [categoryFilter, libraryFilter, workflows])
  const groupedWorkflows = useMemo(() => {
    const groups = new Map<string, NativeApiRunnerWorkflowSummary[]>()
    for (const workflow of visibleWorkflows) {
      const current = groups.get(workflow.category) ?? []
      current.push(workflow)
      groups.set(workflow.category, current)
    }
    return [...groups.entries()]
  }, [visibleWorkflows])
  const currentSnapshot = useMemo(() => graphSnapshot(working), [working])
  const repositoryReadOnly = Boolean(selected?.repository_managed)
  const canRun =
    Boolean(runtime?.ok) &&
    Boolean(analysis?.queueable) &&
    Boolean(validatedSnapshot) &&
    validatedSnapshot === currentSnapshot &&
    !rawDirty &&
    !action
  const currentMediaTargets = analysis?.mediaTargets ?? localFields.filter((field) => {
    const key = field.input.toLowerCase()
    return (
      key.includes('image') ||
      key.includes('video') ||
      key.includes('audio') ||
      key.includes('mask') ||
      key.includes('upload')
    )
  })

  const resetValidation = useCallback(() => {
    setAnalysis(null)
    setValidatedSnapshot('')
    runRequestRef.current = null
  }, [])

  const stageGraph = useCallback(
    (
      graph: WorkflowGraph,
      metadata: {
        nextName: string
        nextVersion?: string
        nextDescription?: string
        nextCategory?: string
        nextSubcategory?: string
        nextEpisode?: string
        nextInstructions?: string
        nextTags?: string[]
        nextSourceFilename?: string | null
        detail?: NativeApiRunnerWorkflowDetail | null
        markDirty?: boolean
      },
    ) => {
      const copy = cloneGraph(graph)
      setWorking(copy)
      setRawJson(JSON.stringify(copy, null, 2))
      setRawDirty(false)
      setName(metadata.nextName)
      setVersion(metadata.nextVersion ?? '1.0')
      setDescription(metadata.nextDescription ?? '')
      setCategory(metadata.nextCategory ?? 'Uncategorized')
      setSubcategory(metadata.nextSubcategory ?? 'General')
      setEpisode(metadata.nextEpisode ?? '')
      setInstructions(metadata.nextInstructions ?? '')
      setTags((metadata.nextTags ?? []).join(', '))
      setSourceFilename(metadata.nextSourceFilename ?? null)
      setSelected(metadata.detail ?? null)
      setDirty(metadata.markDirty ?? true)
      setMode('inputs')
      setFieldFilter('')
      setMediaFile(null)
      setMediaTargetKey('')
      resetValidation()
    },
    [resetValidation],
  )

  const readWorkflowFile = useCallback(
    async (file: File) => {
      setAction('reading-file')
      setError(null)
      setNotice(null)
      try {
        const parsed = JSON.parse(await file.text()) as unknown
        const graph = unwrapGraph(parsed)
        stageGraph(graph, {
          nextName: fileStem(file.name),
          nextDescription: `Loaded from ${file.name}`,
          nextSourceFilename: file.name,
          markDirty: true,
        })
        setNotice(`${file.name} is staged. Validate it, then save it to the shared library.`)
        appendLog(`Loaded operator JSON ${file.name}; no workflow was queued.`)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'The workflow JSON is invalid.')
      } finally {
        setAction('')
      }
    },
    [appendLog, stageGraph],
  )

  const handleWorkflowFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (dirty || rawDirty) {
      setPendingReplacement({ kind: 'file', file })
      return
    }
    void readWorkflowFile(file)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files?.[0]
    if (!file) return
    if (dirty || rawDirty) {
      setPendingReplacement({ kind: 'file', file })
      return
    }
    void readWorkflowFile(file)
  }

  const requestPaste = () => {
    if (dirty || rawDirty) {
      setPendingReplacement({ kind: 'paste' })
      return
    }
    setPasteOpen(true)
  }

  const applyPaste = () => {
    setError(null)
    try {
      const graph = unwrapGraph(JSON.parse(pasteJson) as unknown)
      stageGraph(graph, {
        nextName: 'Pasted workflow',
        nextDescription: 'Pasted into the native CineForge API Runner',
        markDirty: true,
      })
      setPasteOpen(false)
      setPasteJson('')
      setNotice('Pasted JSON is staged. Nothing has been saved or queued.')
      appendLog('Staged pasted API JSON.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The pasted JSON is invalid.')
    }
  }

  const openWorkflow = async (workflowId: string) => {
    setAction('loading-workflow')
    setError(null)
    try {
      const detail = await api.getNativeApiRunnerWorkflow(workflowId)
      stageGraph(detail.workflow, {
        nextName: detail.name,
        nextVersion: detail.version,
        nextDescription: detail.description ?? '',
        nextCategory: detail.category,
        nextSubcategory: detail.subcategory,
        nextEpisode: detail.episode ?? '',
        nextInstructions: detail.instructions ?? '',
        nextTags: detail.tags,
        nextSourceFilename: detail.source_filename,
        detail,
        markDirty: false,
      })
      appendLog(`Opened ${detail.name} from the shared workflow library.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the workflow.')
    } finally {
      setAction('')
    }
  }

  const requestSelection = (workflowId: string) => {
    if (selected?.id === workflowId) return
    if (dirty || rawDirty) {
      setPendingReplacement({ kind: 'workflow', workflowId })
      return
    }
    void openWorkflow(workflowId)
  }

  const discardAndContinue = () => {
    const replacement = pendingReplacement
    const navigation = pendingNavigation
    setPendingReplacement(null)
    setPendingNavigation(null)
    if (navigation) {
      navigation()
      return
    }
    if (replacement?.kind === 'workflow') {
      void openWorkflow(replacement.workflowId)
    } else if (replacement?.kind === 'file') {
      void readWorkflowFile(replacement.file)
    } else if (replacement?.kind === 'paste') {
      setPasteOpen(true)
    }
  }

  const changeField = (field: ApiCallerEditableField, value: string | number | boolean) => {
    if (repositoryReadOnly) return
    setWorking((current) => {
      const graph = cloneGraph(current)
      const node = graph[field.nodeId]
      if (!node) return current
      node.inputs[field.input] = value
      setRawJson(JSON.stringify(graph, null, 2))
      return graph
    })
    setDirty(true)
    setRawDirty(false)
    setNotice(null)
    resetValidation()
  }

  const applyRawJson = () => {
    if (repositoryReadOnly) return
    setError(null)
    try {
      const graph = unwrapGraph(JSON.parse(rawJson) as unknown)
      setWorking(cloneGraph(graph))
      setRawJson(JSON.stringify(graph, null, 2))
      setRawDirty(false)
      setDirty(true)
      resetValidation()
      setNotice('Raw JSON applied. Run live validation before submission.')
      appendLog('Applied edited raw API JSON.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Raw workflow JSON is invalid.')
    }
  }

  const validate = async () => {
    setAction('validating')
    setError(null)
    setNotice(null)
    try {
      const snapshot = currentSnapshot
      const result = await api.analyzeNativeApiRunnerWorkflow(working)
      setAnalysis(result)
      setValidatedSnapshot(snapshot)
      setNotice(
        result.queueable
          ? `Live validation passed: ${result.nodeCount} nodes, ${result.outputNodes.length} outputs.`
          : `Validation found ${result.errorCount} blocking issue${result.errorCount === 1 ? '' : 's'}.`,
      )
      appendLog(
        result.queueable
          ? `Validated ${result.workflowSha256.slice(0, 12)}… against live ComfyUI.`
          : `Validation blocked by ${result.errorCount} issue(s).`,
      )
    } catch (caught) {
      resetValidation()
      setError(caught instanceof Error ? caught.message : 'Live workflow validation failed.')
    } finally {
      setAction('')
    }
  }

  const saveWorkflow = async () => {
    if (!Object.keys(working).length || repositoryReadOnly) return
    const submittedDraft = draftRef.current
    const normalizedTags = tags
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean)
    setAction('saving')
    setError(null)
    setNotice(null)
    try {
      const saved = selected
        ? await api.updateNativeApiRunnerWorkflow(selected.id, {
            name,
            version,
            description,
            category,
            subcategory,
            episode: episode || null,
            instructions,
            tags: normalizedTags,
            requirements: selected.requirements,
            workflow: working,
          })
        : await api.createNativeApiRunnerWorkflow({
            name,
            version,
            description,
            category,
            subcategory,
            episode: episode || null,
            instructions,
            tags: normalizedTags,
            source_filename: sourceFilename,
            workflow: working,
          })
      setSelected(saved)
      const latestDraft = draftRef.current
      const draftUnchanged =
        latestDraft.workflow === submittedDraft.workflow &&
        latestDraft.name === submittedDraft.name &&
        latestDraft.version === submittedDraft.version &&
        latestDraft.description === submittedDraft.description &&
        latestDraft.category === submittedDraft.category &&
        latestDraft.subcategory === submittedDraft.subcategory &&
        latestDraft.episode === submittedDraft.episode &&
        latestDraft.instructions === submittedDraft.instructions &&
        latestDraft.tags === submittedDraft.tags &&
        latestDraft.sourceFilename === submittedDraft.sourceFilename &&
        latestDraft.rawJson === submittedDraft.rawJson &&
        latestDraft.rawDirty === submittedDraft.rawDirty
      if (draftUnchanged) {
        setWorking(cloneGraph(saved.workflow))
        setRawJson(JSON.stringify(saved.workflow, null, 2))
        setDirty(false)
        setRawDirty(false)
      } else {
        setDirty(true)
      }
      await refreshLibrary()
      setNotice(
        draftUnchanged
          ? `${saved.name} saved to the shared workflow library.`
          : `${saved.name} saved, but newer local edits remain unsaved.`,
      )
      appendLog(
        draftUnchanged
          ? `Saved ${saved.name} to the shared native workflow library.`
          : `Saved ${saved.name}; preserved newer unsaved edits in the working copy.`,
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save the workflow.')
    } finally {
      setAction('')
    }
  }

  const saveAsCopy = () => {
    setSelected(null)
    setName(`${name || 'Workflow'} copy`)
    setDirty(true)
    setNotice('Working copy detached. Save to add it as a new library workflow.')
  }

  const downloadJson = () => {
    const blob = new Blob([`${JSON.stringify(working, null, 2)}\n`], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(name || 'sineforge-workflow').replace(/[^a-z0-9_-]+/gi, '-')}.api.json`
    link.click()
    URL.revokeObjectURL(url)
    appendLog('Downloaded the current working graph as API JSON.')
  }

  const downloadSourceJson = () => {
    if (!selected?.source_workflow) return
    const blob = new Blob([`${JSON.stringify(selected.source_workflow, null, 2)}\n`], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${
      (selected.name || 'sineforge-workflow').replace(/[^a-z0-9_-]+/gi, '-')
    }.workflow.json`
    link.click()
    URL.revokeObjectURL(url)
    appendLog('Downloaded the original ComfyUI editor-format workflow JSON.')
  }

  const removeWorkflow = async () => {
    if (!selected || repositoryReadOnly) return
    setConfirmAction(null)
    setAction('removing')
    setError(null)
    try {
      const removed = await api.removeNativeApiRunnerWorkflow(selected.id)
      await refreshLibrary()
      setSelected(null)
      setWorking({})
      setRawJson('')
      setName('')
      setDescription('')
      setCategory('Uncategorized')
      setSubcategory('General')
      setEpisode('')
      setInstructions('')
      setTags('')
      setDirty(false)
      setRawDirty(false)
      resetValidation()
      setNotice(`${removed.name} was archived and removed from the active library.`)
      appendLog(`Archived ${removed.name}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to archive the workflow.')
    } finally {
      setAction('')
    }
  }

  const uploadMedia = async () => {
    if (!mediaFile || !mediaTargetKey || repositoryReadOnly) return
    const field = currentMediaTargets.find(
      (candidate) => `${candidate.nodeId}::${candidate.input}` === mediaTargetKey,
    )
    if (!field) return
    setAction('uploading-media')
    setError(null)
    try {
      const uploaded = await api.uploadNativeApiRunnerMedia(mediaFile)
      const relativeName = uploaded.subfolder
        ? `${uploaded.subfolder}/${uploaded.filename}`
        : uploaded.filename
      changeField(field, relativeName)
      setMediaFile(null)
      if (mediaFileRef.current) mediaFileRef.current.value = ''
      setNotice(`Uploaded ${uploaded.filename} and patched ${field.nodeId}.${field.input}.`)
      appendLog(`Uploaded ${uploaded.filename} to ComfyUI input and patched the working graph.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Media upload failed.')
    } finally {
      setAction('')
    }
  }

  const run = async () => {
    if (!analysis?.queueable || validatedSnapshot !== currentSnapshot) return
    const request =
      runRequestRef.current?.snapshot === currentSnapshot
        ? runRequestRef.current
        : {
            snapshot: currentSnapshot,
            idempotencyKey: makeIdempotencyKey(),
          }
    runRequestRef.current = request
    setAction('submitting')
    setError(null)
    setNotice(null)
    try {
      const result = await api.runNativeApiRunnerWorkflow({
        workflow: working,
        workflow_name: name || 'CineForge native workflow',
        workflow_sha256: analysis.workflowSha256,
        confirmation: true,
        idempotency_key: request.idempotencyKey,
      })
      runRequestRef.current = null
      const activity: RunnerActivity = {
        promptId: result.prompt_id,
        state: 'pending',
        completed: false,
        status: 'queued',
        outputs: [],
        messages: [],
        workflowName: name || 'CineForge native workflow',
        submittedAt: result.submitted_at,
      }
      setActivities((current) => [activity, ...current])
      setNotice(`Queued directly in ComfyUI as ${result.prompt_id}.`)
      appendLog(`Submitted ${result.prompt_id} directly to ComfyUI.`)
      void refreshRuntime(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'ComfyUI submission failed.')
    } finally {
      setAction('')
    }
  }

  const cancelJob = async (job: RunnerActivity, interruptActive: boolean) => {
    setConfirmAction(null)
    setAction(`cancel-${job.promptId}`)
    setError(null)
    try {
      const result = await api.cancelNativeApiRunnerJob(job.promptId, interruptActive)
      if (!result.ok) {
        const latest = await api.getNativeApiRunnerJob(job.promptId)
        setActivities((current) =>
          current.map((item) =>
            item.promptId === job.promptId ? { ...item, ...latest } : item,
          ),
        )
        setNotice(
          `Prompt ${job.promptId} was no longer queued; its current ComfyUI status was refreshed.`,
        )
        appendLog(`Cancel raced with prompt ${job.promptId}; refreshed its status.`)
        return
      }
      setNotice(
        result.action === 'interrupted_active'
          ? `Interrupted active prompt ${job.promptId}.`
          : `Removed pending prompt ${job.promptId}.`,
      )
      appendLog(`${result.action}: ${job.promptId}.`)
      setActivities((current) =>
        current.map((item) =>
          item.promptId === job.promptId
            ? { ...item, state: 'failed', status: result.action }
            : item,
        ),
      )
      void refreshRuntime(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to cancel the prompt.')
    } finally {
      setAction('')
    }
  }

  const freeMemory = async () => {
    setConfirmAction(null)
    setAction('freeing-memory')
    setError(null)
    try {
      await api.freeNativeApiRunnerMemory()
      setNotice('ComfyUI models were unloaded and free-memory collection was requested.')
      appendLog('Requested model unload and VRAM release from ComfyUI.')
      void refreshRuntime(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to release ComfyUI memory.')
    } finally {
      setAction('')
    }
  }

  const hasWorkflow = Object.keys(working).length > 0

  return (
    <div className="page native-runner-page">
      <input
        ref={workflowFileRef}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={handleWorkflowFile}
      />

      <header className="page-title native-runner-title">
        <div>
          <span className="eyebrow">LOCAL COMFYUI EXECUTION</span>
          <h1>CineForge API Runner</h1>
          <p>
            Load, save, inspect, edit, validate, and run API-format workflows without leaving
            CineForge. The standalone ComfyAPI Runner remains separate and unchanged.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn secondary"
            disabled={Boolean(action)}
            onClick={requestPaste}
          >
            Paste JSON
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={Boolean(action)}
            onClick={() => workflowFileRef.current?.click()}
          >
            ＋ Load API JSON
          </button>
        </div>
      </header>

      <RuntimeStrip
        runtime={runtime}
        refreshing={action === 'refreshing-runtime' || action === 'freeing-memory'}
        onRefresh={() => void refreshRuntime()}
        onFreeMemory={() => setConfirmAction({ kind: 'free-memory' })}
      />

      {error ? <ErrorState detail={error} onRetry={() => void loadInitial()} /> : null}
      {notice ? (
        <div className="native-runner-notice" role="status">
          <span aria-hidden="true">◆</span>
          {notice}
          <button type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}>
            ×
          </button>
        </div>
      ) : null}
      {loading ? <LoadingState title="Opening the native API Runner…" /> : null}

      {!loading ? (
        <div className={`native-runner-shell ${hasWorkflow ? 'has-workflow' : ''}`}>
          <aside className="panel native-runner-library">
            <header>
              <div>
                <span className="eyebrow">SHARED WORKFLOW LIBRARY</span>
                <h2>Production workflows</h2>
              </div>
              <span className="native-runner-count">{workflows.length}</span>
            </header>
            <label className="native-runner-search">
              <span>Search library</span>
              <input
                value={libraryFilter}
                placeholder="Name, file, description…"
                onChange={(event) => setLibraryFilter(event.target.value)}
              />
            </label>
            <label className="native-runner-category-filter">
              <span>Category</span>
              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option>All categories</option>
                {categoryOptions.map(([option, count]) => (
                  <option key={option} value={option}>
                    {option} ({count})
                  </option>
                ))}
              </select>
            </label>
            <div className="native-runner-library-list" aria-label="Native workflow library">
              {groupedWorkflows.map(([group, items]) => (
                <section className="native-runner-library-group" key={group}>
                  <header>
                    <span>{group}</span>
                    <small>{items.length}</small>
                  </header>
                  {items.map((workflow) => (
                    <button
                      type="button"
                      key={workflow.id}
                      className={selected?.id === workflow.id ? 'selected' : ''}
                      aria-pressed={selected?.id === workflow.id}
                      disabled={action === 'loading-workflow'}
                      onClick={() => requestSelection(workflow.id)}
                    >
                      <span
                        className="native-runner-file-mark"
                        data-status={workflow.workflow_status}
                        aria-hidden="true"
                      >
                        {'{ }'}
                      </span>
                      <span>
                        <b>{workflow.name}</b>
                        <small>
                          {workflow.episode ?? 'Shared'} · {workflow.subcategory}
                        </small>
                      </span>
                      <span>
                        <small>{workflow.node_count} nodes</small>
                        <i aria-hidden="true">›</i>
                      </span>
                    </button>
                  ))}
                </section>
              ))}
              {!visibleWorkflows.length ? (
                <div className="native-runner-library-empty">
                  <span aria-hidden="true">◇</span>
                  <b>{workflows.length ? 'No match' : 'Library is empty'}</b>
                  <small>
                    {workflows.length
                      ? 'Try another search or category.'
                      : 'Repository and operator workflows appear here.'}
                  </small>
                </div>
              ) : null}
            </div>
            <footer>
              <button
                type="button"
                className="btn secondary"
                disabled={Boolean(action)}
                onClick={() => workflowFileRef.current?.click()}
              >
                Load from disk
              </button>
              <button
                type="button"
                className="btn quiet"
                disabled={Boolean(action)}
                onClick={() => void refreshLibraryFromUi()}
              >
                Refresh
              </button>
            </footer>
          </aside>

          <section className="native-runner-workspace">
            {!hasWorkflow ? (
              <RunnerEmptyState
                hasSavedWorkflows={workflows.length > 0}
                onAdd={() => workflowFileRef.current?.click()}
                onPaste={requestPaste}
                onDrop={handleDrop}
              />
            ) : (
              <div className="native-runner-loaded">
                <section className="panel native-runner-editor">
                  <header className="native-runner-editor-head">
                    <div>
                      <span className="eyebrow">
                        {repositoryReadOnly
                          ? 'READ-ONLY LIBRARY WORKFLOW'
                          : selected
                            ? 'LIBRARY WORKFLOW'
                            : 'UNSAVED DRAFT'}
                      </span>
                      <h2>{name || 'Untitled API workflow'}</h2>
                      <p className="mono">
                        {analysis?.workflowSha256
                          ? `${analysis.workflowSha256.slice(0, 16)}…`
                          : `${Object.keys(working).length} node working copy`}
                      </p>
                    </div>
                    <div>
                      <span className="status-pill" data-status={dirty || rawDirty ? 'review' : 'ready'}>
                        {dirty || rawDirty ? 'Unsaved changes' : 'Saved'}
                      </span>
                      {analysis ? (
                        <span
                          className="status-pill"
                          data-status={analysis.queueable ? 'ready' : 'blocked'}
                        >
                          {analysis.queueable ? 'Validated' : 'Blocked'}
                        </span>
                      ) : null}
                    </div>
                  </header>

                  {repositoryReadOnly ? (
                    <div className="native-runner-read-only-note" role="note">
                      <span aria-hidden="true">◇</span>
                      <div>
                        <b>Protected repository workflow</b>
                        <p>
                          This imported original cannot be edited or archived. Load it in ComfyUI,
                          or use Save as copy to create an editable operator workflow.
                        </p>
                      </div>
                    </div>
                  ) : null}

                  <div className="native-runner-metadata">
                    <label>
                      <span>Workflow name</span>
                      <input
                        value={name}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setName(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label>
                      <span>Version</span>
                      <input
                        value={version}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setVersion(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label>
                      <span>Description</span>
                      <input
                        value={description}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setDescription(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label>
                      <span>Category</span>
                      <input
                        value={category}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setCategory(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label>
                      <span>Subcategory</span>
                      <input
                        value={subcategory}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setSubcategory(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label>
                      <span>Episode / provenance</span>
                      <input
                        value={episode}
                        readOnly={repositoryReadOnly}
                        placeholder="Optional"
                        onChange={(event) => {
                          setEpisode(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label className="native-runner-metadata-wide">
                      <span>Tags</span>
                      <input
                        value={tags}
                        readOnly={repositoryReadOnly}
                        placeholder="Comma-separated tags"
                        onChange={(event) => {
                          setTags(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                    <label className="native-runner-metadata-wide">
                      <span>Operating instructions</span>
                      <textarea
                        value={instructions}
                        readOnly={repositoryReadOnly}
                        onChange={(event) => {
                          setInstructions(event.target.value)
                          setDirty(true)
                        }}
                      />
                    </label>
                  </div>

                  <div className="native-runner-editor-toolbar">
                    <div className="segmented" aria-label="Workflow editor mode">
                      <button
                        type="button"
                        className={mode === 'inputs' ? 'active' : ''}
                        aria-pressed={mode === 'inputs'}
                        disabled={rawDirty}
                        title={rawDirty ? 'Apply or correct the raw JSON before leaving this editor' : undefined}
                        onClick={() => setMode('inputs')}
                      >
                        Editable inputs
                      </button>
                      <button
                        type="button"
                        className={mode === 'json' ? 'active' : ''}
                        aria-pressed={mode === 'json'}
                        onClick={() => setMode('json')}
                      >
                        Raw API JSON
                      </button>
                    </div>
                    {mode === 'inputs' ? (
                      <label>
                        <span className="sr-only">Filter editable inputs</span>
                        <input
                          value={fieldFilter}
                          placeholder="Filter inputs…"
                          onChange={(event) => setFieldFilter(event.target.value)}
                        />
                      </label>
                    ) : null}
                    <span>
                      {Object.keys(working).length} nodes · {editableFields.length} primitive inputs
                    </span>
                  </div>

                  {mode === 'json' ? (
                    <div className="native-runner-json-editor">
                      <textarea
                        aria-label="Raw API workflow JSON"
                        className="mono"
                        value={rawJson}
                        readOnly={repositoryReadOnly}
                        spellCheck={false}
                        onChange={(event) => {
                          setRawJson(event.target.value)
                          setRawDirty(true)
                          setDirty(true)
                          resetValidation()
                        }}
                      />
                      <div>
                        <span>
                          {rawDirty
                            ? 'Apply this JSON before validating or running.'
                            : 'The editor is synchronized with the rendered fields.'}
                        </span>
                        <button
                          type="button"
                          className="btn secondary"
                          disabled={!rawDirty || repositoryReadOnly}
                          onClick={applyRawJson}
                        >
                          Apply JSON
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="native-runner-node-list">
                      {groupedFields.map(([nodeId, fields]) => (
                        <article key={nodeId} className="native-runner-node">
                          <header>
                            <span className="mono">{nodeId}</span>
                            <div>
                              <b>{fields[0]?.title}</b>
                              <small>{fields[0]?.classType}</small>
                            </div>
                            <span>{fields.length} editable</span>
                          </header>
                          <div>
                            {fields.map((field) => {
                              const currentValue =
                                working[field.nodeId]?.inputs[field.input] ?? field.value
                              return (
                                <label key={`${field.nodeId}-${field.input}`}>
                                  <span>{field.input}</span>
                                  {field.valueType === 'bool' ? (
                                    <select
                                      value={String(currentValue)}
                                      disabled={repositoryReadOnly}
                                      onChange={(event) =>
                                        changeField(field, event.target.value === 'true')
                                      }
                                    >
                                      <option value="true">true</option>
                                      <option value="false">false</option>
                                    </select>
                                  ) : isLongField(field) ? (
                                    <textarea
                                      value={String(currentValue)}
                                      readOnly={repositoryReadOnly}
                                      onChange={(event) => changeField(field, event.target.value)}
                                    />
                                  ) : (
                                    <input
                                      type={
                                        field.valueType === 'int' || field.valueType === 'float'
                                          ? 'number'
                                          : 'text'
                                      }
                                      step={field.valueType === 'float' ? 'any' : undefined}
                                      value={String(currentValue)}
                                      readOnly={repositoryReadOnly}
                                      onChange={(event) => {
                                        if (
                                          field.valueType === 'int' ||
                                          field.valueType === 'float'
                                        ) {
                                          const number = Number(event.target.value)
                                          if (!Number.isNaN(number)) changeField(field, number)
                                        } else {
                                          changeField(field, event.target.value)
                                        }
                                      }}
                                    />
                                  )}
                                </label>
                              )
                            })}
                          </div>
                        </article>
                      ))}
                      {!groupedFields.length ? (
                        <EmptyState
                          title="No editable inputs match"
                          detail="Clear the input filter or use Raw API JSON for connection-only nodes."
                        />
                      ) : null}
                    </div>
                  )}

                  <footer className="native-runner-editor-actions">
                    <div>
                      {selected && !repositoryReadOnly ? (
                        <button
                          type="button"
                          className="btn danger"
                          disabled={Boolean(action)}
                          onClick={() => setConfirmAction({ kind: 'remove' })}
                        >
                          Archive
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn quiet"
                        disabled={Boolean(action) || rawDirty}
                        onClick={downloadJson}
                      >
                        Download JSON
                      </button>
                      {selected?.source_workflow ? (
                        <button
                          type="button"
                          className="btn quiet"
                          disabled={Boolean(action)}
                          onClick={downloadSourceJson}
                        >
                          Original workflow
                        </button>
                      ) : null}
                      {selected?.repository_managed && selected.source_workflow ? (
                        <a
                          className="btn native-runner-comfy-load"
                          href={nativeApiRunnerWorkflowOpenUrl(selected.id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-disabled={Boolean(action) || !runtime?.ok}
                          tabIndex={Boolean(action) || !runtime?.ok ? -1 : undefined}
                          title={
                            runtime?.ok
                              ? 'Open the original editable graph in the active ComfyUI instance'
                              : 'Start or reconnect ComfyUI first'
                          }
                          onClick={(event) => {
                            if (action || !runtime?.ok) {
                              event.preventDefault()
                              return
                            }
                            setError(null)
                            setNotice(
                              `${selected.name} is opening on the ComfyUI canvas. Nothing was queued.`,
                            )
                            appendLog(
                              `Sent ${selected.name} to the ComfyUI canvas without queueing it.`,
                            )
                          }}
                        >
                          Load in ComfyUI
                        </a>
                      ) : null}
                    </div>
                    <div>
                      {selected ? (
                        <button
                          type="button"
                          className="btn secondary"
                          disabled={Boolean(action)}
                          onClick={saveAsCopy}
                        >
                          Save as copy
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn primary"
                        disabled={
                          Boolean(action) ||
                          rawDirty ||
                          repositoryReadOnly ||
                          !name.trim() ||
                          (!dirty && Boolean(selected))
                        }
                        onClick={() => void saveWorkflow()}
                      >
                        {action === 'saving'
                          ? 'Saving…'
                          : selected
                            ? 'Save workflow'
                            : 'Save to library'}
                      </button>
                    </div>
                  </footer>
                </section>

                <aside className="native-runner-inspector">
                  <section className="panel native-runner-guide-card">
                    <header>
                      <div>
                        <span className="eyebrow">WORKFLOW GUIDE</span>
                        <h2>About & setup</h2>
                      </div>
                      {selected?.repository_managed ? (
                        <span className="native-runner-repository-badge">
                          Read-only library
                        </span>
                      ) : (
                        <span className="native-runner-repository-badge">Operator</span>
                      )}
                    </header>

                    <div className="native-runner-guide-tags">
                      <span>{category || 'Uncategorized'}</span>
                      <span>{subcategory || 'General'}</span>
                      {episode ? <span>{episode}</span> : null}
                      {selected?.workflow_status === 'requires_custom_nodes' ? (
                        <span data-status="blocked">Needs node mapping</span>
                      ) : (
                        <span data-status="ready">API converted</span>
                      )}
                    </div>

                    <p className="native-runner-guide-description">
                      {description || 'Add a detailed description for this workflow.'}
                    </p>

                    {selected ? (
                      <dl className="native-runner-guide-source">
                        <div>
                          <dt>Source</dt>
                          <dd>{selected.source_archive ?? selected.source_filename ?? 'Operator import'}</dd>
                        </div>
                        <div>
                          <dt>Entry</dt>
                          <dd>{selected.source_entry ?? selected.source_filename ?? '—'}</dd>
                        </div>
                      </dl>
                    ) : null}

                    <div className="native-runner-guide-section">
                      <h3>Requirements</h3>
                      {selected?.requirements.unresolved_node_classes?.length ? (
                        <div className="native-runner-requirement-alert">
                          <b>Resolve custom nodes before running</b>
                          <span>
                            {selected.requirements.unresolved_node_classes.join(', ')}
                          </span>
                        </div>
                      ) : (
                        <p>
                          Validate against the connected ComfyUI install before queueing.
                        </p>
                      )}
                      {selected?.requirements.model_files?.length ? (
                        <div className="native-runner-requirement-list">
                          {selected.requirements.model_files.slice(0, 8).map((model, index) => (
                            <span key={`${model.node_id ?? 'model'}-${model.input ?? index}-${index}`}>
                              <b>{model.input ?? 'model'}</b>
                              <small>{model.value ?? 'Select an installed file'}</small>
                            </span>
                          ))}
                          {selected.requirements.model_files.length > 8 ? (
                            <i>+{selected.requirements.model_files.length - 8} more model references</i>
                          ) : null}
                        </div>
                      ) : null}
                      {selected?.requirements.custom_node_root ? (
                        <code>{selected.requirements.custom_node_root}</code>
                      ) : null}
                    </div>

                    <div className="native-runner-guide-section">
                      <h3>How to use</h3>
                      <ol>
                        {(instructions || '1. Validate the workflow, edit its inputs, and run one job.')
                          .split('\n')
                          .map((step) => step.replace(/^\d+\.\s*/, '').trim())
                          .filter(Boolean)
                          .map((step, index) => (
                            <li key={`${index}-${step.slice(0, 24)}`}>{step}</li>
                          ))}
                      </ol>
                    </div>

                    {selected?.requirements.documentation_notes ? (
                      <details className="native-runner-source-notes">
                        <summary>Source-pack notes</summary>
                        <pre>{selected.requirements.documentation_notes}</pre>
                      </details>
                    ) : null}
                  </section>

                  <section className="panel native-runner-run-card">
                    <header>
                      <div>
                        <span className="eyebrow">VALIDATE & RUN</span>
                        <h2>Execution</h2>
                      </div>
                      <span
                        className="native-runner-execution-mark"
                        data-ready={canRun}
                        aria-hidden="true"
                      >
                        ▶
                      </span>
                    </header>

                    <div className="native-runner-run-facts">
                      <div>
                        <span>Target</span>
                        <b>ComfyUI direct</b>
                      </div>
                      <div>
                        <span>Queue unit</span>
                        <b>1 workflow</b>
                      </div>
                      <div>
                        <span>Output nodes</span>
                        <b>{analysis?.outputNodes.length ?? '—'}</b>
                      </div>
                      <div>
                        <span>Model refs</span>
                        <b>{analysis?.modelRefs.length ?? '—'}</b>
                      </div>
                    </div>

                    {analysis ? (
                      <div
                        className="native-runner-validation"
                        data-pass={analysis.queueable}
                      >
                        <span aria-hidden="true">{analysis.queueable ? '✓' : '!'}</span>
                        <div>
                          <b>
                            {analysis.queueable
                              ? 'Live validation passed'
                              : `${analysis.errorCount} blocking issue${analysis.errorCount === 1 ? '' : 's'}`}
                          </b>
                          <small>
                            {analysis.warningCount} warning{analysis.warningCount === 1 ? '' : 's'} ·
                            {' '}
                            {analysis.workflowSha256.slice(0, 12)}…
                          </small>
                        </div>
                      </div>
                    ) : (
                      <div className="native-runner-validation" data-pass="idle">
                        <span aria-hidden="true">◇</span>
                        <div>
                          <b>Validation required</b>
                          <small>Checked against the connected ComfyUI node registry.</small>
                        </div>
                      </div>
                    )}

                    {analysis?.issues.length ? (
                      <div className="native-runner-issues">
                        {analysis.issues.slice(0, 6).map((issue, index) => (
                          <article
                            key={`${issue.code}-${issue.nodeId ?? 'graph'}-${index}`}
                            data-severity={issue.severity}
                          >
                            <span>{issue.severity === 'error' ? '!' : 'i'}</span>
                            <div>
                              <b>{issue.code.replaceAll('_', ' ')}</b>
                              <small>{issue.message}</small>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : null}

                    <div className="native-runner-run-actions">
                      <button
                        type="button"
                        className="btn secondary"
                        disabled={Boolean(action) || rawDirty || !runtime?.ok}
                        onClick={() => void validate()}
                      >
                        {action === 'validating' ? 'Validating…' : 'Validate live'}
                      </button>
                      <button
                        type="button"
                        className="btn primary"
                        disabled={!canRun}
                        title={
                          canRun
                            ? 'Queue this exact validated graph'
                            : 'Validate the current JSON against a ready ComfyUI runtime first'
                        }
                        onClick={() => void run()}
                      >
                        {action === 'submitting' ? 'Submitting…' : 'Run workflow'}
                      </button>
                    </div>
                    <p className="native-runner-run-note">
                      Every click submits exactly one validated graph. Editing any input invalidates
                      the prior check.
                    </p>
                  </section>

                  <section className="panel native-runner-media-card">
                    <header className="panel-head">
                      <div>
                        <h2>Media input</h2>
                        <p>Upload to ComfyUI and patch a detected input</p>
                      </div>
                      <span className="status-pill" data-status="local">Local</span>
                    </header>
                    <label>
                      <span>Target input</span>
                      <select
                        value={mediaTargetKey}
                        disabled={!currentMediaTargets.length || repositoryReadOnly}
                        onChange={(event) => setMediaTargetKey(event.target.value)}
                      >
                        <option value="">
                          {currentMediaTargets.length
                            ? 'Select a media input…'
                            : 'No media inputs detected'}
                        </option>
                        {currentMediaTargets.map((target) => (
                          <option
                            key={`${target.nodeId}-${target.input}`}
                            value={`${target.nodeId}::${target.input}`}
                          >
                            {target.nodeId} · {target.title} · {target.input}
                          </option>
                        ))}
                      </select>
                    </label>
                    <input
                      ref={mediaFileRef}
                      type="file"
                      aria-label="Media file to upload"
                      accept="image/png,image/jpeg,image/webp,image/gif,image/bmp,audio/*,video/*,.mkv,.flac,.m4a"
                      disabled={repositoryReadOnly}
                      onChange={(event) => setMediaFile(event.target.files?.[0] ?? null)}
                    />
                    <button
                      type="button"
                      className="btn secondary"
                      disabled={
                        !mediaFile ||
                        !mediaTargetKey ||
                        Boolean(action) ||
                        repositoryReadOnly
                      }
                      onClick={() => void uploadMedia()}
                    >
                      {action === 'uploading-media' ? 'Uploading…' : 'Upload & patch JSON'}
                    </button>
                  </section>

                  <section className="panel native-runner-model-card">
                    <header className="panel-head">
                      <div>
                        <h2>Models & resources</h2>
                        <p>Live selector availability from ComfyUI</p>
                      </div>
                      <span>{analysis?.modelRefs.length ?? 0}</span>
                    </header>
                    {analysis?.modelRefs.length ? (
                      <div>
                        {analysis.modelRefs.slice(0, 8).map((model) => (
                          <article key={`${model.nodeId}-${model.input}`}>
                            <i
                              data-state={
                                model.available === false
                                  ? 'missing'
                                  : model.available === true
                                    ? 'ready'
                                    : 'unknown'
                              }
                            />
                            <div>
                              <b>{model.name}</b>
                              <small>
                                {model.nodeId} · {model.input}
                              </small>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p className="native-runner-muted">
                        Validate to inspect model and resource selectors.
                      </p>
                    )}
                  </section>
                </aside>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {!loading ? (
        <section className="native-runner-bottom-grid">
          <div className="panel native-runner-queue">
            <header className="panel-head">
              <div>
                <h2>Queue & outputs</h2>
                <p>Tracked directly from ComfyUI with no standalone Runner dependency</p>
              </div>
              <span className="status-pill" data-status={activities.length ? 'ready' : 'draft'}>
                {activities.length} this session
              </span>
            </header>
            {activities.length ? (
              <div className="native-runner-job-list" aria-live="polite">
                {activities.map((job) => (
                  <article key={job.promptId} data-state={job.state}>
                    <header>
                      <span className="native-runner-job-state" aria-hidden="true">
                        {job.state === 'completed'
                          ? '✓'
                          : job.state === 'failed'
                            ? '!'
                            : '↻'}
                      </span>
                      <div>
                        <b>{job.workflowName}</b>
                        <small className="mono">{job.promptId}</small>
                      </div>
                      <span className="status-pill" data-status={job.state === 'completed' ? 'ready' : job.state === 'failed' ? 'blocked' : 'review'}>
                        {activityStateLabel(job.state)}
                      </span>
                      {job.state === 'pending' ? (
                        <button
                          type="button"
                          className="btn quiet"
                          disabled={Boolean(action)}
                          onClick={() => void cancelJob(job, false)}
                        >
                          Cancel
                        </button>
                      ) : job.state === 'running' ? (
                        <small title="Active ComfyUI interruption is global and is intentionally not exposed here.">
                          Active in ComfyUI
                        </small>
                      ) : null}
                    </header>
                    {job.outputs.length ? (
                      <div className="native-runner-output-grid">
                        {job.outputs.map((output) => {
                          const url = nativeApiRunnerOutputUrl(job.promptId, output)
                          const kind = outputKind(output.filename)
                          return (
                            <figure key={`${output.nodeId}-${output.kind}-${output.filename}`}>
                              {kind === 'image' ? (
                                <img src={url} alt={output.filename} />
                              ) : kind === 'video' ? (
                                <video src={url} controls preload="metadata" />
                              ) : kind === 'audio' ? (
                                <audio src={url} controls preload="metadata" />
                              ) : (
                                <span aria-hidden="true">{'{ }'}</span>
                              )}
                              <figcaption>
                                <b>{output.filename}</b>
                                <a href={url} target="_blank" rel="noreferrer">
                                  Open output
                                </a>
                              </figcaption>
                            </figure>
                          )
                        })}
                      </div>
                    ) : (
                      <p>
                        {job.state === 'completed'
                          ? 'Completed without a file output in ComfyUI history.'
                          : `Submitted ${formatDate(job.submittedAt)} · waiting for outputs`}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <div className="native-runner-queue-empty">
                <span aria-hidden="true">▷</span>
                <div>
                  <b>No native submissions this session</b>
                  <p>Validate an exact working graph, then run it once to create a queue card.</p>
                </div>
              </div>
            )}
          </div>

          <div className="panel native-runner-log">
            <header className="panel-head">
              <div>
                <h2>Operator log</h2>
                <p>Session-only actions and validation events</p>
              </div>
              <button type="button" className="btn quiet" onClick={() => setLogs([])}>
                Clear
              </button>
            </header>
            <div className="mono" role="log" aria-label="Native Runner operator log">
              {logs.length ? (
                logs.map((entry, index) => <p key={`${entry}-${index}`}>{entry}</p>)
              ) : (
                <p>No session events.</p>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {pasteOpen ? (
        <div className="native-runner-modal-backdrop">
          <section className="native-runner-modal" role="dialog" aria-modal="true" aria-labelledby="paste-json-title">
            <span className="eyebrow">NEW WORKING COPY</span>
            <h2 id="paste-json-title">Paste API workflow JSON</h2>
            <p>
              This creates an unsaved draft only. Visual workflow JSON is rejected; use ComfyUI
              Dev Mode → Save (API Format).
            </p>
            <textarea
              className="mono"
              aria-label="Paste API workflow JSON"
              autoFocus
              value={pasteJson}
              placeholder={'{\n  "1": {\n    "class_type": "…",\n    "inputs": {}\n  }\n}'}
              onChange={(event) => setPasteJson(event.target.value)}
            />
            <div className="modal-actions">
              <button
                type="button"
                className="btn secondary"
                onClick={() => {
                  setPasteOpen(false)
                  setPasteJson('')
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!pasteJson.trim()}
                onClick={applyPaste}
              >
                Stage JSON
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {pendingReplacement || pendingNavigation ? (
        <div className="native-runner-modal-backdrop">
          <section className="native-runner-modal compact" role="dialog" aria-modal="true" aria-labelledby="discard-title">
            <span className="eyebrow">UNSAVED CHANGES</span>
            <h2 id="discard-title">Discard the current working copy?</h2>
            <p>
              Your edits have not been saved to the shared workflow library. Continuing will replace or
              leave this working copy.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn secondary"
                autoFocus
                onClick={() => {
                  setPendingReplacement(null)
                  setPendingNavigation(null)
                }}
              >
                Keep editing
              </button>
              <button type="button" className="btn danger" onClick={discardAndContinue}>
                Discard & continue
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {confirmAction ? (
        <div className="native-runner-modal-backdrop">
          <section className="native-runner-modal compact" role="dialog" aria-modal="true" aria-labelledby="confirm-action-title">
            <span className="eyebrow">CONFIRM LOCAL ACTION</span>
            <h2 id="confirm-action-title">
              {confirmAction.kind === 'remove'
                ? `Archive ${selected?.name ?? 'workflow'}?`
                : 'Unload models and free VRAM?'}
            </h2>
            <p>
              {confirmAction.kind === 'remove'
                ? 'The record leaves the active library but remains recoverable in CineForge’s archive.'
                : 'ComfyUI will unload active models only when its running and pending queues are both empty. No workflow files are changed.'}
            </p>
            <div className="modal-actions">
              <button type="button" className="btn secondary" onClick={() => setConfirmAction(null)}>
                Cancel
              </button>
              <button
                type="button"
                className={confirmAction.kind === 'remove' ? 'btn danger' : 'btn primary'}
                onClick={() => {
                  if (confirmAction.kind === 'remove') void removeWorkflow()
                  else {
                    void freeMemory()
                  }
                }}
              >
                {confirmAction.kind === 'remove'
                  ? 'Archive workflow'
                  : 'Unload & free VRAM'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
