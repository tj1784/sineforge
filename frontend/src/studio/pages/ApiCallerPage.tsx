import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react'
import {
  api,
  type ApiCallerAnalysis,
  type ApiCallerEditableField,
  type ApiCallerRuntime,
  type ApiCallerRunResult,
  type ApiCallerWorkflowDetail,
  type ApiCallerWorkflowNode,
  type ApiCallerWorkflowSummary,
} from '../../api/client'
import { formatDate } from '../../components/formatDate'
import { EmptyState, ErrorState, LoadingState } from '../components/StateBlocks'

type WorkflowGraph = Record<string, ApiCallerWorkflowNode>
type EditorMode = 'fields' | 'json'

function cloneGraph(workflow: WorkflowGraph): WorkflowGraph {
  return JSON.parse(JSON.stringify(workflow)) as WorkflowGraph
}

function unwrapGraph(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Workflow JSON must be an object.')
  }
  const object = value as Record<string, unknown>
  if (object.prompt && typeof object.prompt === 'object' && !Array.isArray(object.prompt)) {
    return object.prompt as Record<string, unknown>
  }
  if (object.workflow && typeof object.workflow === 'object' && !Array.isArray(object.workflow)) {
    const hasNodes = Object.values(object).some(
      (node) => node && typeof node === 'object' && !Array.isArray(node) && 'class_type' in node,
    )
    if (!hasNodes) return object.workflow as Record<string, unknown>
  }
  return object
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

function isLongText(field: ApiCallerEditableField): boolean {
  const key = `${field.input} ${field.title} ${field.classType}`.toLowerCase()
  return (
    String(field.value).length > 120 ||
    key.includes('prompt') ||
    key.includes('text') ||
    key.includes('negative') ||
    key.includes('positive')
  )
}

function fileStem(filename: string): string {
  return filename.replace(/\.(api\.)?json$/i, '').replace(/[_-]+/g, ' ').trim() || 'Imported workflow'
}

export function ApiCallerPage() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [workflows, setWorkflows] = useState<ApiCallerWorkflowSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [selected, setSelected] = useState<ApiCallerWorkflowDetail | null>(null)
  const [working, setWorking] = useState<WorkflowGraph>({})
  const [name, setName] = useState('')
  const [version, setVersion] = useState('1.0')
  const [description, setDescription] = useState('')
  const [rawJson, setRawJson] = useState('{}')
  const [analysis, setAnalysis] = useState<ApiCallerAnalysis | null>(null)
  const [runtime, setRuntime] = useState<ApiCallerRuntime | null>(null)
  const [mode, setMode] = useState<EditorMode>('fields')
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [queueCount, setQueueCount] = useState(1)
  const [mergeMovie, setMergeMovie] = useState(false)
  const [varySeed, setVarySeed] = useState(false)
  const [saveLatents, setSaveLatents] = useState(false)
  const [runResult, setRunResult] = useState<ApiCallerRunResult | null>(null)

  const loadLibrary = useCallback(async (preferredId?: string) => {
    setLoading(true)
    setError(null)
    try {
      const [items, runtimeResult] = await Promise.all([
        api.listApiCallerWorkflows(),
        api.getApiCallerRuntime().catch(() => null),
      ])
      setWorkflows(items)
      setRuntime(runtimeResult)
      setSelectedId((current) => {
        const candidate = preferredId || current
        if (candidate && items.some((item) => item.id === candidate)) return candidate
        return items[0]?.id ?? ''
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the API workflow library.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadLibrary(), 0)
    return () => window.clearTimeout(timer)
  }, [loadLibrary])

  useEffect(() => {
    if (!selectedId) return
    let active = true
    const timer = window.setTimeout(() => {
      setAction('loading-workflow')
      setError(null)
      void api
        .getApiCallerWorkflow(selectedId)
        .then((detail) => {
          if (!active) return
          const graph = cloneGraph(detail.workflow)
          setSelected(detail)
          setWorking(graph)
          setName(detail.name)
          setVersion(detail.version)
          setDescription(detail.description ?? '')
          setRawJson(JSON.stringify(graph, null, 2))
          setDirty(false)
          setRunResult(null)
          return api.analyzeApiCallerWorkflow(graph).then((result) => {
            if (active) setAnalysis(result)
          })
        })
        .catch((caught) => {
          if (!active) return
          setAnalysis(null)
          setError(caught instanceof Error ? caught.message : 'Unable to load the selected workflow.')
        })
        .finally(() => {
          if (active) setAction('')
        })
    }, 0)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [selectedId])

  const derivedFields = useMemo(() => editableWorkflowFields(working), [working])
  const editableFields = analysis?.editable?.length ? analysis.editable : derivedFields
  const groupedFields = useMemo(() => {
    const groups = new Map<string, ApiCallerEditableField[]>()
    for (const field of editableFields) {
      const values = groups.get(field.nodeId) ?? []
      values.push(field)
      groups.set(field.nodeId, values)
    }
    return [...groups.entries()]
  }, [editableFields])

  const visibleWorkflows = useMemo(() => {
    const query = filter.trim().toLowerCase()
    if (!query) return workflows
    return workflows.filter((workflow) =>
      `${workflow.name} ${workflow.description ?? ''} ${workflow.source_id ?? ''}`
        .toLowerCase()
        .includes(query),
    )
  }, [filter, workflows])

  const changeField = (field: ApiCallerEditableField, next: string | number | boolean) => {
    setWorking((current) => {
      const graph = cloneGraph(current)
      const node = graph[field.nodeId]
      if (!node) return current
      node.inputs[field.input] = next
      setRawJson(JSON.stringify(graph, null, 2))
      return graph
    })
    setDirty(true)
    setAnalysis(null)
    setNotice(null)
  }

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setAction('importing-file')
    setError(null)
    setNotice(null)
    try {
      const parsed = JSON.parse(await file.text()) as unknown
      const graph = unwrapGraph(parsed)
      const created = await api.createApiCallerWorkflow({
        name: fileStem(file.name),
        version: '1.0',
        description: `Imported from ${file.name}`,
        source_filename: file.name,
        workflow: graph,
      })
      setNotice(`Added ${created.name}.`)
      await loadLibrary(created.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The workflow could not be imported.')
    } finally {
      setAction('')
    }
  }

  const importRunnerLibrary = async () => {
    setAction('importing-runner')
    setError(null)
    setNotice(null)
    try {
      const result = await api.importApiCallerRunnerWorkflows()
      setNotice(
        `Runner library synced: ${result.imported} added, ${result.updated} updated, ${result.skipped} non-API workflow(s) skipped.`,
      )
      await loadLibrary(result.workflows[0]?.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to import Runner workflows.')
    } finally {
      setAction('')
    }
  }

  const applyRawJson = () => {
    try {
      const parsed = unwrapGraph(JSON.parse(rawJson))
      const graph = parsed as WorkflowGraph
      const fields = editableWorkflowFields(graph)
      if (!Object.keys(graph).length || !fields.length) {
        throw new Error('No editable API-format nodes were found.')
      }
      setWorking(graph)
      setDirty(true)
      setAnalysis(null)
      setNotice('Raw JSON applied to the working copy. Save to persist it.')
      setMode('fields')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Raw JSON is invalid.')
    }
  }

  const save = async () => {
    if (!selected) return
    setAction('saving')
    setError(null)
    setNotice(null)
    try {
      const updated = await api.updateApiCallerWorkflow(selected.id, {
        name,
        version,
        description,
        workflow: working,
      })
      setSelected(updated)
      setWorking(cloneGraph(updated.workflow))
      setRawJson(JSON.stringify(updated.workflow, null, 2))
      setDirty(false)
      setNotice(`Saved ${updated.name}.`)
      await loadLibrary(updated.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save the workflow.')
    } finally {
      setAction('')
    }
  }

  const analyze = async () => {
    setAction('analyzing')
    setError(null)
    setNotice(null)
    try {
      const result = await api.analyzeApiCallerWorkflow(working)
      setAnalysis(result)
      setNotice(
        result.queueable
          ? `Validation passed: ${result.nodeCount} nodes and ${result.editable.length} editable inputs.`
          : 'The Runner recognized this workflow, but it is not queueable API JSON.',
      )
    } catch (caught) {
      setAnalysis(null)
      setError(caught instanceof Error ? caught.message : 'Workflow validation failed.')
    } finally {
      setAction('')
    }
  }

  const queue = async () => {
    if (!selected) return
    setAction('queueing')
    setError(null)
    setNotice(null)
    setRunResult(null)
    try {
      const result = await api.runApiCallerWorkflow({
        workflow: working,
        workflow_name: name || selected.name,
        queue_count: queueCount,
        merge_movie: mergeMovie,
        vary_seed: varySeed,
        save_latents: saveLatents,
      })
      setRunResult(result)
      setNotice(
        result.jobId
          ? `Queued in ComfyAPI Runner as job ${result.jobId}.`
          : 'Workflow accepted by ComfyAPI Runner.',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Workflow submission failed.')
    } finally {
      setAction('')
    }
  }

  const remove = async () => {
    if (!selected) return
    if (!window.confirm(`Remove “${selected.name}” from the SineForge API Caller library?`)) return
    setAction('removing')
    setError(null)
    try {
      const result = await api.removeApiCallerWorkflow(selected.id)
      setNotice(`${result.name} was removed from the active library and archived locally.`)
      setSelected(null)
      setSelectedId('')
      await loadLibrary()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to remove the workflow.')
    } finally {
      setAction('')
    }
  }

  return (
    <div className="page api-caller-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">LOCAL COMFYUI OPERATOR</span>
          <h1>API Caller</h1>
          <p>
            Import and manage API-format workflows, adjust node inputs in the right-hand editor,
            validate them through ComfyAPI Runner, then explicitly send them to ComfyUI.
          </p>
        </div>
        <div className="page-actions">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(event) => void handleFile(event)}
          />
          <button
            type="button"
            className="btn secondary"
            disabled={Boolean(action)}
            onClick={() => fileInputRef.current?.click()}
          >
            Add API JSON
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={Boolean(action)}
            onClick={() => void importRunnerLibrary()}
          >
            {action === 'importing-runner' ? 'Syncing…' : 'Import Runner library'}
          </button>
        </div>
      </div>

      <div className="api-caller-runtime" data-status={runtime?.runner.comfy_connected ? 'ready' : 'review'}>
        <i aria-hidden="true" />
        <span>
          <b>{runtime?.runner.comfy_connected ? 'ComfyUI connected' : 'Runtime connection unavailable'}</b>
          <small>
            Runner {runtime?.runner_url ?? 'http://127.0.0.1:8022'} · ComfyUI{' '}
            {runtime?.comfy_url ?? 'http://127.0.0.1:8888'}
          </small>
        </span>
        <span className="status-pill" data-status={runtime?.runner.reachable ? 'ready' : 'review'}>
          {runtime?.runner.status ?? 'checking'}
        </span>
      </div>

      {error ? <ErrorState detail={error} onRetry={() => setError(null)} /> : null}
      {notice ? <div className="api-caller-notice">{notice}</div> : null}
      {loading ? <LoadingState title="Loading API workflow library…" /> : null}

      {!loading ? (
        <div className="api-caller-layout">
          <aside className="panel api-caller-library">
            <header className="panel-head">
              <div>
                <h2>Workflow library</h2>
                <p>{workflows.length} operator workflow{workflows.length === 1 ? '' : 's'}</p>
              </div>
              <button
                type="button"
                className="btn secondary"
                disabled={Boolean(action)}
                onClick={() => void loadLibrary()}
              >
                Refresh
              </button>
            </header>
            <label className="api-caller-search">
              <span>Filter workflows</span>
              <input
                value={filter}
                placeholder="WAN, FLUX, Krea…"
                onChange={(event) => setFilter(event.target.value)}
              />
            </label>
            <div className="api-caller-workflow-list">
              {visibleWorkflows.map((workflow) => (
                <button
                  type="button"
                  key={workflow.id}
                  className={selectedId === workflow.id ? 'selected' : ''}
                  onClick={() => setSelectedId(workflow.id)}
                >
                  <span>
                    <b>{workflow.name}</b>
                    <small>
                      v{workflow.version} · {workflow.node_count} nodes
                    </small>
                  </span>
                  <span>
                    <small>{workflow.source_kind === 'comfy_api_runner_static' ? 'Runner' : 'Local'}</small>
                    <small>{formatDate(workflow.updated_at)}</small>
                  </span>
                </button>
              ))}
              {!visibleWorkflows.length ? (
                <EmptyState
                  title={workflows.length ? 'No workflow matches' : 'No API workflows yet'}
                  detail={
                    workflows.length
                      ? 'Clear the filter to see the library.'
                      : 'Add an API JSON file or import the connected Runner library.'
                  }
                />
              ) : null}
            </div>
          </aside>

          <section className="panel api-caller-editor">
            {selected ? (
              <>
                <header className="api-caller-editor-head">
                  <div>
                    <span className="eyebrow">EDITABLE WORKFLOW</span>
                    <h2>{selected.name}</h2>
                    <p className="mono">{selected.sha256.slice(0, 16)}…</p>
                  </div>
                  <div className="page-actions">
                    <span className="status-pill" data-status={dirty ? 'review' : 'ready'}>
                      {dirty ? 'Unsaved changes' : 'Saved'}
                    </span>
                    <button
                      type="button"
                      className="btn secondary danger"
                      disabled={Boolean(action)}
                      onClick={() => void remove()}
                    >
                      Remove
                    </button>
                  </div>
                </header>

                <div className="api-caller-metadata form-grid three">
                  <label>
                    Name
                    <input
                      value={name}
                      onChange={(event) => {
                        setName(event.target.value)
                        setDirty(true)
                      }}
                    />
                  </label>
                  <label>
                    Version
                    <input
                      value={version}
                      onChange={(event) => {
                        setVersion(event.target.value)
                        setDirty(true)
                      }}
                    />
                  </label>
                  <label>
                    Description
                    <input
                      value={description}
                      onChange={(event) => {
                        setDescription(event.target.value)
                        setDirty(true)
                      }}
                    />
                  </label>
                </div>

                <div className="api-caller-toolbar">
                  <div className="segmented">
                    <button
                      type="button"
                      className={mode === 'fields' ? 'active' : ''}
                      onClick={() => setMode('fields')}
                    >
                      Rendered inputs
                    </button>
                    <button
                      type="button"
                      className={mode === 'json' ? 'active' : ''}
                      onClick={() => setMode('json')}
                    >
                      Raw API JSON
                    </button>
                  </div>
                  <span>
                    {Object.keys(working).length} nodes · {editableFields.length} editable values
                  </span>
                </div>

                {mode === 'json' ? (
                  <div className="api-caller-raw">
                    <textarea
                      className="prompt mono"
                      value={rawJson}
                      spellCheck={false}
                      onChange={(event) => setRawJson(event.target.value)}
                    />
                    <button type="button" className="btn secondary" onClick={applyRawJson}>
                      Apply JSON to working copy
                    </button>
                  </div>
                ) : (
                  <div className="api-caller-node-list">
                    {groupedFields.map(([nodeId, fields]) => (
                      <article key={nodeId} className="api-caller-node">
                        <header>
                          <span className="mono">{nodeId}</span>
                          <div>
                            <b>{fields[0]?.title}</b>
                            <small>{fields[0]?.classType}</small>
                          </div>
                          <small>{fields.length} input{fields.length === 1 ? '' : 's'}</small>
                        </header>
                        <div className="api-caller-node-fields">
                          {fields.map((field) => (
                            <label key={`${field.nodeId}-${field.input}`}>
                              <span>{field.input}</span>
                              {field.valueType === 'bool' ? (
                                <select
                                  value={String(working[field.nodeId]?.inputs[field.input] ?? field.value)}
                                  onChange={(event) => changeField(field, event.target.value === 'true')}
                                >
                                  <option value="true">true</option>
                                  <option value="false">false</option>
                                </select>
                              ) : isLongText(field) ? (
                                <textarea
                                  value={String(working[field.nodeId]?.inputs[field.input] ?? field.value)}
                                  onChange={(event) => changeField(field, event.target.value)}
                                />
                              ) : (
                                <input
                                  type={field.valueType === 'int' || field.valueType === 'float' ? 'number' : 'text'}
                                  step={field.valueType === 'float' ? 'any' : undefined}
                                  value={String(working[field.nodeId]?.inputs[field.input] ?? field.value)}
                                  onChange={(event) => {
                                    if (field.valueType === 'int' || field.valueType === 'float') {
                                      const number = Number(event.target.value)
                                      if (!Number.isNaN(number)) changeField(field, number)
                                      return
                                    }
                                    changeField(field, event.target.value)
                                  }}
                                />
                              )}
                            </label>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                )}

                <div className="api-caller-submit">
                  <div className="form-grid three">
                    <label>
                      Queue count
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={queueCount}
                        onChange={(event) =>
                          setQueueCount(Math.max(1, Math.min(50, Number(event.target.value) || 1)))
                        }
                      />
                    </label>
                    <label className="api-caller-check">
                      <input
                        type="checkbox"
                        checked={varySeed}
                        onChange={(event) => setVarySeed(event.target.checked)}
                      />
                      Vary seed per queued run
                    </label>
                    <label className="api-caller-check">
                      <input
                        type="checkbox"
                        checked={saveLatents}
                        onChange={(event) => setSaveLatents(event.target.checked)}
                      />
                      Save latents
                    </label>
                  </div>
                  <label className="api-caller-check">
                    <input
                      type="checkbox"
                      checked={mergeMovie}
                      onChange={(event) => setMergeMovie(event.target.checked)}
                    />
                    Merge movie when multiple queued clips complete
                  </label>
                  <div className="api-caller-submit-actions">
                    <button
                      type="button"
                      className="btn secondary"
                      disabled={Boolean(action)}
                      onClick={() => void analyze()}
                    >
                      {action === 'analyzing' ? 'Validating…' : 'Validate'}
                    </button>
                    <button
                      type="button"
                      className="btn secondary"
                      disabled={Boolean(action) || !dirty}
                      onClick={() => void save()}
                    >
                      {action === 'saving' ? 'Saving…' : 'Save workflow'}
                    </button>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={Boolean(action) || analysis?.queueable === false}
                      onClick={() => void queue()}
                    >
                      {action === 'queueing' ? 'Sending…' : `Queue ${queueCount}`}
                    </button>
                  </div>
                  {analysis ? (
                    <div className={`validation ${analysis.queueable ? 'pass' : 'fail'}`}>
                      <span aria-hidden="true">{analysis.queueable ? '✓' : '!'}</span>
                      <span>
                        <b>{analysis.queueable ? 'Runner validation passed' : 'Workflow is not queueable'}</b>
                        <small>
                          {analysis.nodeCount} nodes · {analysis.modelRefs.length} model references ·{' '}
                          {analysis.outputNodes.length} output nodes
                        </small>
                      </span>
                    </div>
                  ) : null}
                  {runResult ? (
                    <pre className="api-caller-result">{JSON.stringify(runResult, null, 2)}</pre>
                  ) : null}
                </div>
              </>
            ) : (
              <EmptyState
                title="Select or add a workflow"
                detail="The selected API graph will render here with editable node inputs before anything is sent."
              />
            )}
          </section>
        </div>
      ) : null}
    </div>
  )
}
