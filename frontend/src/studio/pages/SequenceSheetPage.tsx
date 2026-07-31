import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react'
import {
  api,
  type SequenceSheetDryRunResponse,
  type SequenceSheetExecuteResponse,
  type SequenceSheetRow,
  type SequenceSheetSeed,
} from '../../api/client'
import { useStudio } from '../StudioState'
import {
  LTX_SEQUENCE_MODEL_PROFILE,
  LTX_SEQUENCE_TEMPLATE_KEY,
  SEQUENCE_MAX_DURATION_SEC,
  SEQUENCE_MIN_DURATION_SEC,
  buildSequenceSheetRequest,
  createSequenceRow,
  dryRunPassed,
  parseSequenceSheetImport,
  remoteSequenceIssues,
  renumberSequenceRows,
  sequenceSheetSignature,
  validateSequenceRows,
} from '../sequenceSheet'
import './SequenceSheetPage.css'

type SequenceAction = '' | 'dry-run' | 'execute'

let executionKeyCounter = 0

function splitIds(value: string): string[] {
  return value
    .split(/[|;,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function responseStatus(
  result: SequenceSheetDryRunResponse | SequenceSheetExecuteResponse | null,
): string {
  if (!result) return 'Not run'
  if (typeof result.status === 'string' && result.status.trim()) return result.status
  return result.ok === false ? 'Failed' : 'Accepted'
}

function executionIdempotencyKey(signature: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < signature.length; index += 1) {
    hash ^= signature.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  executionKeyCounter += 1
  return [
    'sequence',
    (hash >>> 0).toString(16).padStart(8, '0'),
    Date.now().toString(36),
    executionKeyCounter.toString(36),
  ].join('-')
}

function loadDraft(projectId: string): SequenceSheetRow[] {
  const fallback = [createSequenceRow(1)]
  try {
    const raw = window.localStorage.getItem(`sineforge.sequence-sheet.v1:${projectId}`)
    if (!raw) return fallback
    return parseSequenceSheetImport(raw, 'sequence-sheet-draft.json')
  } catch {
    return fallback
  }
}

export function SequenceSheetPage() {
  const { projectId, data } = useStudio()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const executionRequestRef = useRef({ signature: '', idempotencyKey: '' })
  const [rows, setRows] = useState<SequenceSheetRow[]>(() => loadDraft(projectId))
  const [selectedRowId, setSelectedRowId] = useState(() => rows[0]?.row_id ?? '')
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<string | null>(null)
  const [action, setAction] = useState<SequenceAction>('')
  const [dryRunResult, setDryRunResult] = useState<SequenceSheetDryRunResponse | null>(null)
  const [executeResult, setExecuteResult] = useState<SequenceSheetExecuteResponse | null>(null)
  const [validatedSignature, setValidatedSignature] = useState('')

  const selectedRow = rows.find((row) => row.row_id === selectedRowId) ?? rows[0] ?? null
  const selectedIndex = selectedRow
    ? rows.findIndex((row) => row.row_id === selectedRow.row_id)
    : -1
  const localIssues = useMemo(() => validateSequenceRows(rows), [rows])
  const localErrors = localIssues.filter((issue) => issue.level === 'error')
  const remoteIssues = useMemo(() => remoteSequenceIssues(dryRunResult), [dryRunResult])
  const enabledRows = rows.filter((row) => row.enabled)
  const totalDuration = enabledRows.reduce((total, row) => total + row.duration_sec, 0)
  const currentSignature = useMemo(
    () => sequenceSheetSignature(projectId, rows),
    [projectId, rows],
  )
  const canExecute =
    localErrors.length === 0 &&
    validatedSignature === currentSignature &&
    dryRunResult != null &&
    dryRunPassed(dryRunResult)

  const persistRows = useCallback((nextRows: SequenceSheetRow[]) => {
    const normalized = renumberSequenceRows(nextRows)
    setRows(normalized)
    try {
      window.localStorage.setItem(
        `sineforge.sequence-sheet.v1:${projectId}`,
        JSON.stringify(buildSequenceSheetRequest(projectId, normalized)),
      )
    } catch {
      // The editor remains usable when browser storage is unavailable.
    }
    setDryRunResult(null)
    setExecuteResult(null)
    setValidatedSignature('')
    setRequestError(null)
    executionRequestRef.current = { signature: '', idempotencyKey: '' }
  }, [projectId])

  const updateRow = useCallback(
    (rowId: string, patch: Partial<SequenceSheetRow>) => {
      persistRows(rows.map((row) => (row.row_id === rowId ? { ...row, ...patch } : row)))
    },
    [persistRows, rows],
  )

  const addRow = () => {
    const next = createSequenceRow(rows.length + 1)
    persistRows([...rows, next])
    setSelectedRowId(next.row_id)
  }

  const duplicateSelected = () => {
    if (!selectedRow) return
    const duplicate = createSequenceRow(rows.length + 1, {
      ...selectedRow,
      output_name: `${selectedRow.output_name}_copy`,
      continuity_source: 'previous_last_frame',
    })
    const insertionIndex = selectedIndex + 1
    persistRows([
      ...rows.slice(0, insertionIndex),
      duplicate,
      ...rows.slice(insertionIndex),
    ])
    setSelectedRowId(duplicate.row_id)
  }

  const removeRow = (rowId: string) => {
    const index = rows.findIndex((row) => row.row_id === rowId)
    const next = rows.filter((row) => row.row_id !== rowId)
    persistRows(next)
    if (rowId === selectedRowId) {
      setSelectedRowId(next[Math.min(index, next.length - 1)]?.row_id ?? '')
    }
  }

  const moveRow = (rowId: string, offset: -1 | 1) => {
    const index = rows.findIndex((row) => row.row_id === rowId)
    const target = index + offset
    if (index < 0 || target < 0 || target >= rows.length) return
    const next = [...rows]
    ;[next[index], next[target]] = [next[target], next[index]]
    persistRows(next)
  }

  const applyImport = (text: string, filename = '') => {
    try {
      const imported = parseSequenceSheetImport(text, filename)
      persistRows(imported)
      setSelectedRowId(imported[0]?.row_id ?? '')
      setImportError(null)
      setImportText('')
    } catch (caught) {
      setImportError(caught instanceof Error ? caught.message : 'Unable to import the sequence sheet.')
    }
  }

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      applyImport(await file.text(), file.name)
    } catch (caught) {
      setImportError(caught instanceof Error ? caught.message : 'Unable to read the import file.')
    }
  }

  const runDryRun = async () => {
    if (localErrors.length) {
      setRequestError('Resolve the local validation errors before requesting a dry run.')
      return
    }
    setAction('dry-run')
    setRequestError(null)
    setExecuteResult(null)
    const signature = currentSignature
    try {
      const result = await api.dryRunSequenceSheet(
        projectId,
        buildSequenceSheetRequest(projectId, rows),
      )
      setDryRunResult(result)
      setValidatedSignature(dryRunPassed(result) ? signature : '')
    } catch (caught) {
      setDryRunResult(null)
      setValidatedSignature('')
      setRequestError(caught instanceof Error ? caught.message : 'Sequence dry run failed.')
    } finally {
      setAction('')
    }
  }

  const execute = async () => {
    if (!canExecute) {
      setRequestError('Run and pass a dry run for the current rows before execution.')
      return
    }
    const confirmed = window.confirm(
      `Queue ${enabledRows.length} LTX segment${enabledRows.length === 1 ? '' : 's'} (${totalDuration.toFixed(1)} seconds planned)?`,
    )
    if (!confirmed) return

    setAction('execute')
    setRequestError(null)
    try {
      if (executionRequestRef.current.signature !== currentSignature) {
        executionRequestRef.current = {
          signature: currentSignature,
          idempotencyKey: executionIdempotencyKey(currentSignature),
        }
      }
      const result = await api.executeSequenceSheet(
        projectId,
        {
          ...buildSequenceSheetRequest(projectId, rows),
          idempotency_key: executionRequestRef.current.idempotencyKey,
          allow_rendering: true,
        },
      )
      setExecuteResult(result)
    } catch (caught) {
      setRequestError(caught instanceof Error ? caught.message : 'Sequence execution failed.')
    } finally {
      setAction('')
    }
  }

  const setInputAsset = (value: string) => {
    if (!selectedRow) return
    const continuity =
      selectedRow.continuity_source.startsWith('asset:') ||
      (selectedIndex === 0 && selectedRow.continuity_source === 'none')
        ? value
          ? (`asset:${value}` as const)
          : 'none'
        : selectedRow.continuity_source
    updateRow(selectedRow.row_id, {
      input_asset_id: value || null,
      continuity_source: continuity,
    })
  }

  if (!data) return null

  return (
    <div className="page sequence-sheet-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">LONG VIDEO · LTX ONLY</span>
          <h1>Sequence Sheet</h1>
          <p>
            Build an ordered LTX I2V run using typed rows, explicit continuity sources, and a
            required dry run before queue submission.
          </p>
        </div>
        <div className="page-actions">
          <input
            ref={fileInputRef}
            className="sequence-file-input"
            type="file"
            accept=".csv,.json,text/csv,application/json"
            onChange={(event) => void handleFile(event)}
            aria-label="Import sequence CSV or JSON file"
          />
          <button type="button" className="btn secondary" onClick={() => fileInputRef.current?.click()}>
            Import file
          </button>
          <button type="button" className="btn secondary" onClick={addRow}>
            Add row
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={action !== '' || localErrors.length > 0}
            onClick={() => void runDryRun()}
          >
            {action === 'dry-run' ? 'Checking…' : 'Dry run'}
          </button>
        </div>
      </div>

      <section className="sequence-model-boundary" aria-label="Sequence model boundary">
        <div>
          <span className="status-pill" data-status="ready">LTX I2V</span>
          <strong>{SEQUENCE_MIN_DURATION_SEC}–{SEQUENCE_MAX_DURATION_SEC} seconds per row</strong>
          <p>
            Longer story beats are composed from sequential model-safe rows; each row records its
            continuity source and output name. Native LTX audio stays synchronized with every row
            through the final mux; WAN Phase 8 is not used.
          </p>
        </div>
        <div data-status="hold">
          <span className="status-pill" data-status="disabled">WAN on hold</span>
          <p>WAN is not selectable, and WAN imports are rejected rather than rewritten.</p>
        </div>
      </section>

      <div className="sequence-metrics" aria-label="Sequence summary">
        <div><span>Rows</span><strong>{rows.length}</strong></div>
        <div><span>Enabled</span><strong>{enabledRows.length}</strong></div>
        <div><span>Planned duration</span><strong>{totalDuration.toFixed(1)}s</strong></div>
        <div>
          <span>Dry-run state</span>
          <strong>{validatedSignature === currentSignature ? responseStatus(dryRunResult) : 'Required'}</strong>
        </div>
      </div>

      <div className="sequence-sheet-layout">
        <main className="sequence-sheet-main">
          <details className="panel sequence-import-panel">
            <summary>
              <span>
                <strong>Paste CSV or JSON</strong>
                <small>Canonical JSON rows or a header-based CSV are accepted.</small>
              </span>
            </summary>
            <div className="sequence-import-body">
              <label>
                <span>Import content</span>
                <textarea
                  value={importText}
                  onChange={(event) => {
                    setImportText(event.target.value)
                    setImportError(null)
                  }}
                  rows={7}
                  placeholder={'output_name,prompt,duration_sec,seed,input_asset_id\nOpening,"The subject walks toward the car.",10,derive,asset-id'}
                />
              </label>
              <div className="sequence-inline-actions">
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => applyImport(importText)}
                >
                  Replace rows from text
                </button>
                <small>
                  Lists such as character_ids use semicolons or pipes in CSV.
                </small>
              </div>
              {importError ? <p className="sequence-inline-error" role="alert">{importError}</p> : null}
            </div>
          </details>

          <section className="panel sequence-rows-panel" aria-labelledby="sequence-rows-title">
            <header className="panel-head">
              <div>
                <h2 id="sequence-rows-title">Ordered LTX rows</h2>
                <p>Edit the common fields here; select a row for full workflow and continuity details.</p>
              </div>
              <button type="button" className="btn secondary" onClick={duplicateSelected} disabled={!selectedRow}>
                Duplicate selected
              </button>
            </header>

            <div className="sequence-row-head" aria-hidden="true">
              <span>Use</span>
              <span>Order / output</span>
              <span>Prompt</span>
              <span>Duration</span>
              <span>Continuity</span>
              <span>Actions</span>
            </div>

            <div className="sequence-row-list">
              {rows.map((row, index) => {
                const rowIssues = localIssues.filter((issue) => issue.row_id === row.row_id)
                return (
                  <article
                    key={row.row_id}
                    className={row.row_id === selectedRow?.row_id ? 'sequence-row selected' : 'sequence-row'}
                    data-status={rowIssues.some((issue) => issue.level === 'error') ? 'error' : 'ready'}
                  >
                    <label className="sequence-enable">
                      <input
                        type="checkbox"
                        checked={row.enabled}
                        onChange={(event) => updateRow(row.row_id, { enabled: event.target.checked })}
                        aria-label={`Enable ${row.output_name || `row ${index + 1}`}`}
                      />
                    </label>
                    <div className="sequence-row-name">
                      <button
                        type="button"
                        className="sequence-order-button"
                        onClick={() => setSelectedRowId(row.row_id)}
                        aria-label={`Inspect row ${index + 1}`}
                      >
                        {index + 1}
                      </button>
                      <input
                        value={row.output_name}
                        onFocus={() => setSelectedRowId(row.row_id)}
                        onChange={(event) => updateRow(row.row_id, { output_name: event.target.value })}
                        aria-label={`Output name row ${index + 1}`}
                      />
                      <small className="mono" title={row.row_id}>{row.row_id}</small>
                    </div>
                    <label className="sequence-prompt-cell">
                      <span className="sr-only">Prompt row {index + 1}</span>
                      <textarea
                        rows={2}
                        value={row.prompt}
                        onFocus={() => setSelectedRowId(row.row_id)}
                        onChange={(event) => updateRow(row.row_id, { prompt: event.target.value })}
                        aria-label={`Prompt row ${index + 1}`}
                        placeholder="Describe chronological visible motion and relevant sound."
                      />
                    </label>
                    <label className="sequence-duration-cell">
                      <span className="sr-only">Duration row {index + 1}</span>
                      <input
                        type="number"
                        min={SEQUENCE_MIN_DURATION_SEC}
                        max={SEQUENCE_MAX_DURATION_SEC}
                        step="0.5"
                        value={row.duration_sec}
                        onFocus={() => setSelectedRowId(row.row_id)}
                        onChange={(event) => updateRow(row.row_id, { duration_sec: Number(event.target.value) })}
                        aria-label={`Duration row ${index + 1}`}
                      />
                      <small>seconds</small>
                    </label>
                    <button
                      type="button"
                      className="sequence-continuity-button"
                      onClick={() => setSelectedRowId(row.row_id)}
                    >
                      {row.continuity_source === 'previous_last_frame'
                        ? 'Previous last frame'
                        : row.continuity_source.startsWith('asset:')
                          ? 'Input asset'
                          : row.continuity_source.startsWith('row:')
                            ? 'Selected row'
                            : 'None'}
                    </button>
                    <div className="sequence-row-actions">
                      <button
                        type="button"
                        onClick={() => moveRow(row.row_id, -1)}
                        disabled={index === 0}
                        aria-label={`Move row ${index + 1} up`}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => moveRow(row.row_id, 1)}
                        disabled={index === rows.length - 1}
                        aria-label={`Move row ${index + 1} down`}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        onClick={() => removeRow(row.row_id)}
                        aria-label={`Remove row ${index + 1}`}
                      >
                        ×
                      </button>
                    </div>
                    {rowIssues.length ? (
                      <ul className="sequence-row-issues">
                        {rowIssues.map((issue, issueIndex) => (
                          <li key={`${issue.code ?? 'issue'}-${issueIndex}`} data-level={issue.level}>
                            {issue.message}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                )
              })}
            </div>

            {!rows.length ? (
              <div className="empty-state">
                <strong>No rows</strong>
                <p>Add a native row or import LTX sequence data.</p>
                <button type="button" className="btn primary" onClick={addRow}>Add first row</button>
              </div>
            ) : null}
          </section>

          <section className="panel sequence-validation-panel" aria-labelledby="sequence-validation-title">
            <header className="panel-head">
              <div>
                <h2 id="sequence-validation-title">Validation and queue status</h2>
                <p>Execution remains locked until the current payload passes a server dry run.</p>
              </div>
              <span
                className="status-pill"
                data-status={localErrors.length ? 'blocked' : canExecute ? 'ready' : 'review'}
              >
                {localErrors.length ? `${localErrors.length} local error${localErrors.length === 1 ? '' : 's'}` : canExecute ? 'Ready to execute' : 'Dry run required'}
              </span>
            </header>

            {requestError ? <p className="sequence-request-error" role="alert">{requestError}</p> : null}

            <div className="sequence-validation-columns">
              <div>
                <h3>Local contract</h3>
                {localIssues.length ? (
                  <ul className="sequence-issue-list">
                    {localIssues.map((issue, index) => (
                      <li key={`${issue.row_id ?? 'sheet'}-${issue.code ?? index}`} data-level={issue.level}>
                        <strong>{issue.level}</strong>
                        <span>{issue.message}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="sequence-valid-message">All local LTX row checks pass.</p>
                )}
              </div>
              <div>
                <h3>Server dry run</h3>
                {remoteIssues.length ? (
                  <ul className="sequence-issue-list">
                    {remoteIssues.map((issue, index) => (
                      <li
                        key={`${issue.row_id ?? 'remote'}-${issue.code ?? index}`}
                        data-level={issue.level ?? issue.severity ?? 'warning'}
                      >
                        <strong>{issue.level ?? issue.severity ?? 'review'}</strong>
                        <span>{issue.message}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="sequence-valid-message">
                    {dryRunResult
                      ? `Server status: ${responseStatus(dryRunResult)}.`
                      : 'No server dry run has been requested for this draft.'}
                  </p>
                )}
              </div>
            </div>

            <div className="sequence-submit-bar">
              <div>
                <strong>{enabledRows.length} LTX segment{enabledRows.length === 1 ? '' : 's'}</strong>
                <span>{totalDuration.toFixed(1)} seconds planned · project {projectId}</span>
              </div>
              <button
                type="button"
                className="btn secondary"
                disabled={action !== '' || localErrors.length > 0}
                onClick={() => void runDryRun()}
              >
                {action === 'dry-run' ? 'Dry-running…' : 'Dry run current rows'}
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!canExecute || action !== ''}
                onClick={() => void execute()}
                title={canExecute ? 'Queue the validated LTX sequence' : 'Pass a dry run for the current rows first'}
              >
                {action === 'execute' ? 'Queueing…' : 'Execute LTX sequence'}
              </button>
            </div>

            {executeResult ? (
              <details className="sequence-result">
                <summary>Execution response · {responseStatus(executeResult)}</summary>
                <pre>{JSON.stringify(executeResult, null, 2)}</pre>
              </details>
            ) : dryRunResult ? (
              <details className="sequence-result">
                <summary>Dry-run response · {responseStatus(dryRunResult)}</summary>
                <pre>{JSON.stringify(dryRunResult, null, 2)}</pre>
              </details>
            ) : null}
          </section>
        </main>

        <aside className="panel sequence-inspector" aria-label="Workflow and row details">
          {selectedRow ? (
            <>
              <header className="panel-head">
                <div>
                  <span className="eyebrow">WORKFLOW / ROW DETAILS</span>
                  <h2>{selectedRow.output_name || `Row ${selectedIndex + 1}`}</h2>
                  <p className="mono">{selectedRow.row_id}</p>
                </div>
                <span className="status-pill" data-status={selectedRow.enabled ? 'ready' : 'disabled'}>
                  {selectedRow.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </header>

              <div className="sequence-workflow-lock">
                <div>
                  <span>Model family</span>
                  <strong>LTX</strong>
                </div>
                <div>
                  <span>Mode</span>
                  <strong>I2V</strong>
                </div>
                <div>
                  <span>Duration contract</span>
                  <strong>{SEQUENCE_MIN_DURATION_SEC}–{SEQUENCE_MAX_DURATION_SEC}s</strong>
                </div>
                <p>WAN is intentionally unavailable in this editor.</p>
              </div>

              <div className="sequence-inspector-fields">
                <label>
                  <span>Output name</span>
                  <input
                    value={selectedRow.output_name}
                    onChange={(event) => updateRow(selectedRow.row_id, { output_name: event.target.value })}
                  />
                </label>
                <div className="sequence-field-pair">
                  <label>
                    <span>Scene ID</span>
                    <input
                      value={selectedRow.scene_id ?? ''}
                      onChange={(event) => updateRow(selectedRow.row_id, { scene_id: event.target.value || null })}
                      placeholder="Optional"
                    />
                  </label>
                  <label>
                    <span>Subscene ID</span>
                    <input
                      value={selectedRow.subscene_id ?? ''}
                      onChange={(event) => updateRow(selectedRow.row_id, { subscene_id: event.target.value || null })}
                      placeholder="Optional"
                    />
                  </label>
                </div>
                <label>
                  <span>LTX video prompt</span>
                  <textarea
                    rows={7}
                    value={selectedRow.prompt}
                    onChange={(event) => updateRow(selectedRow.row_id, { prompt: event.target.value })}
                    placeholder="Chronological action, camera behavior, visible continuity, and relevant sound."
                  />
                </label>
                <label>
                  <span>Negative prompt</span>
                  <textarea
                    rows={3}
                    value={selectedRow.negative_prompt ?? ''}
                    onChange={(event) => updateRow(selectedRow.row_id, { negative_prompt: event.target.value || null })}
                    placeholder="Optional"
                  />
                </label>
                <div className="sequence-field-pair">
                  <label>
                    <span>Duration (seconds)</span>
                    <input
                      type="number"
                      min={SEQUENCE_MIN_DURATION_SEC}
                      max={SEQUENCE_MAX_DURATION_SEC}
                      step="0.5"
                      value={selectedRow.duration_sec}
                      onChange={(event) => updateRow(selectedRow.row_id, { duration_sec: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    <span>Seed</span>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={selectedRow.seed === 'derive' ? '' : selectedRow.seed}
                      onChange={(event) => {
                        const value = event.target.value.trim()
                        const seed: SequenceSheetSeed =
                          !value ? 'derive' : Number(value)
                        updateRow(selectedRow.row_id, { seed })
                      }}
                      placeholder="Derived when blank"
                    />
                  </label>
                </div>
                <label>
                  <span>Input asset ID</span>
                  <input
                    value={selectedRow.input_asset_id ?? ''}
                    onChange={(event) => setInputAsset(event.target.value.trim())}
                    placeholder="Managed starting-image asset ID"
                  />
                </label>
                <label>
                  <span>Continuity source</span>
                  <select
                    value={selectedRow.continuity_source}
                    onChange={(event) => updateRow(selectedRow.row_id, {
                      continuity_source: event.target.value as SequenceSheetRow['continuity_source'],
                    })}
                  >
                    <option value="none">None</option>
                    <option value="previous_last_frame" disabled={selectedIndex === 0}>
                      Previous enabled row · last frame
                    </option>
                    {selectedRow.input_asset_id ? (
                      <option value={`asset:${selectedRow.input_asset_id}`}>
                        Input asset · {selectedRow.input_asset_id}
                      </option>
                    ) : null}
                    {rows.slice(0, selectedIndex).map((row) => (
                      <option key={row.row_id} value={`row:${row.row_id}:last_frame`}>
                        Row {row.order} · {row.output_name} · last frame
                      </option>
                    ))}
                  </select>
                </label>
                <div className="sequence-field-pair">
                  <label>
                    <span>Template key</span>
                    <input value={LTX_SEQUENCE_TEMPLATE_KEY} readOnly />
                  </label>
                  <label>
                    <span>Workflow version</span>
                    <input
                      value={selectedRow.workflow_version ?? ''}
                      onChange={(event) => updateRow(selectedRow.row_id, { workflow_version: event.target.value || null })}
                      placeholder="Backend default"
                    />
                  </label>
                </div>
                <label>
                  <span>Model profile</span>
                  <input value={LTX_SEQUENCE_MODEL_PROFILE} readOnly />
                </label>
                <label>
                  <span>Character IDs</span>
                  <input
                    value={selectedRow.character_ids.join('; ')}
                    onChange={(event) => updateRow(selectedRow.row_id, { character_ids: splitIds(event.target.value) })}
                    placeholder="character-id-1; character-id-2"
                  />
                </label>
                <label>
                  <span>Asset IDs</span>
                  <input
                    value={selectedRow.asset_ids.join('; ')}
                    onChange={(event) => updateRow(selectedRow.row_id, { asset_ids: splitIds(event.target.value) })}
                    placeholder="prop-id; location-id"
                  />
                </label>
                <label>
                  <span>Reference asset IDs</span>
                  <input
                    value={selectedRow.reference_asset_ids.join('; ')}
                    onChange={(event) => updateRow(selectedRow.row_id, { reference_asset_ids: splitIds(event.target.value) })}
                    placeholder="reference-id-1; reference-id-2"
                  />
                </label>
                <div className="sequence-field-pair">
                  <label>
                    <span>Maximum attempts</span>
                    <input
                      type="number"
                      min="1"
                      max="5"
                      value={selectedRow.max_attempts ?? 2}
                      onChange={(event) => updateRow(selectedRow.row_id, { max_attempts: Number(event.target.value) })}
                    />
                  </label>
                  <label>
                    <span>On error</span>
                    <select
                      value={selectedRow.on_error ?? 'stop'}
                      onChange={(event) => updateRow(selectedRow.row_id, { on_error: event.target.value })}
                    >
                      <option value="stop">Stop sequence</option>
                      <option value="skip">Skip row</option>
                    </select>
                  </label>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <strong>Select a row</strong>
              <p>Choose or create a row to inspect its LTX workflow contract.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
