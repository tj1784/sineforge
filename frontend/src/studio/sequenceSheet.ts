import {
  SEQUENCE_SHEET_SCHEMA_VERSION,
  type SequenceSheetContinuitySource,
  type SequenceSheetDryRunResponse,
  type SequenceSheetRequest,
  type SequenceSheetRow,
  type SequenceSheetSeed,
  type SequenceSheetValidationIssue,
} from '../api/client'

export const SEQUENCE_MIN_DURATION_SEC = 8
export const SEQUENCE_MAX_DURATION_SEC = 15
export const LTX_SEQUENCE_TEMPLATE_KEY = 'ltx-i2v'
export const LTX_SEQUENCE_MODEL_PROFILE = 'ltx_base@2'
export const LTX_SEQUENCE_WORKFLOW_VERSION = '1.0'
export const LTX_SEQUENCE_WORKFLOW_SHA256 =
  'c928366ccf42a2d47a81a51c478079c385d1d6e72fe50ed8ff96d51c4dbb68bc'
const SAFE_OUTPUT_NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$/
const WINDOWS_RESERVED_OUTPUT_NAMES = new Set([
  'CON',
  'PRN',
  'AUX',
  'NUL',
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
])

export type LocalSequenceIssue = SequenceSheetValidationIssue & {
  level: 'error' | 'warning'
}

let localRowCounter = 0

function localRowId(): string {
  localRowCounter += 1
  return `ltx-row-${Date.now().toString(36)}-${localRowCounter}`
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Each imported sequence row must be an object.')
  }
  return value as Record<string, unknown>
}

function asText(value: unknown): string {
  if (value == null) return ''
  return String(value).trim()
}

function asOptionalText(value: unknown): string | null {
  const text = asText(value)
  return text || null
}

function asBoolean(value: unknown, fallback = true): boolean {
  if (typeof value === 'boolean') return value
  if (value == null || value === '') return fallback
  const normalized = String(value).trim().toLowerCase()
  if (['true', 'yes', '1', 'enabled', 'on'].includes(normalized)) return true
  if (['false', 'no', '0', 'disabled', 'off'].includes(normalized)) return false
  throw new Error(`Unable to read "${String(value)}" as a boolean.`)
}

function asNumber(value: unknown, fallback: number): number {
  if (value == null || value === '') return fallback
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    throw new Error(`Unable to read "${String(value)}" as a number.`)
  }
  return parsed
}

function asInteger(value: unknown, fallback: number): number {
  const parsed = asNumber(value, fallback)
  if (!Number.isInteger(parsed)) {
    throw new Error(`Expected an integer, received "${String(value)}".`)
  }
  return parsed
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(asText).filter(Boolean)
  }
  const text = asText(value)
  if (!text) return []
  return text
    .split(/[|;]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function asSeed(value: unknown): SequenceSheetSeed {
  const text = asText(value)
  if (!text || text.toLowerCase() === 'derive') return 'derive'
  const parsed = Number(text)
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`Seed "${text}" must be "derive" or a non-negative safe integer.`)
  }
  return parsed
}

function asContinuitySource(
  value: unknown,
  rowIndex: number,
  inputAssetId: string | null,
): SequenceSheetContinuitySource {
  const text = asText(value)
  if (!text) {
    if (rowIndex === 0) return inputAssetId ? `asset:${inputAssetId}` : 'none'
    return 'previous_last_frame'
  }

  const normalized = text.toLowerCase().replaceAll(' ', '_')
  if (normalized === 'none') return 'none'
  if (['previous', 'previous_frame', 'previous_last_frame'].includes(normalized)) {
    return 'previous_last_frame'
  }
  if (normalized === 'asset' && inputAssetId) return `asset:${inputAssetId}`
  if (/^asset:[^:]+$/i.test(text)) return text as `asset:${string}`
  if (/^row:[^:]+:last_frame$/i.test(text)) return text as `row:${string}:last_frame`

  throw new Error(
    `Continuity source "${text}" is unsupported. Use none, previous_last_frame, asset:<id>, or row:<id>:last_frame.`,
  )
}

function assertLtxOnly(templateKey: string, modelProfile: string, mode: string): void {
  if (!templateKey.toLowerCase().includes('ltx') || templateKey.toLowerCase().includes('wan')) {
    throw new Error(`Template "${templateKey}" is not allowed. Sequence Sheet is LTX-only; WAN is on hold.`)
  }
  if (!modelProfile.toLowerCase().includes('ltx') || modelProfile.toLowerCase().includes('wan')) {
    throw new Error(`Model profile "${modelProfile}" is not allowed. Sequence Sheet is LTX-only.`)
  }
  if (mode.toLowerCase() !== 'i2v') {
    throw new Error(`Mode "${mode}" is not allowed. This Sequence Sheet currently supports LTX I2V only.`)
  }
}

function normalizeImportedRow(value: unknown, rowIndex: number): SequenceSheetRow {
  const row = asObject(value)
  const inputAssetId = asOptionalText(row.input_asset_id ?? row.starting_image_asset_id)
  const templateKey = asText(row.template_key) || LTX_SEQUENCE_TEMPLATE_KEY
  const modelProfile = asText(row.model_profile) || LTX_SEQUENCE_MODEL_PROFILE
  const mode = asText(row.mode) || 'i2v'
  assertLtxOnly(templateKey, modelProfile, mode)

  return {
    row_id: asText(row.row_id ?? row.id) || localRowId(),
    order: rowIndex + 1,
    enabled: asBoolean(row.enabled, true),
    scene_id: asOptionalText(row.scene_id),
    subscene_id: asOptionalText(row.subscene_id),
    template_key: templateKey,
    workflow_version: asOptionalText(row.workflow_version) || LTX_SEQUENCE_WORKFLOW_VERSION,
    workflow_sha256: asOptionalText(row.workflow_sha256) || LTX_SEQUENCE_WORKFLOW_SHA256,
    model_profile: modelProfile,
    mode: 'i2v',
    prompt: asText(row.prompt ?? row.video_prompt),
    negative_prompt: asOptionalText(row.negative_prompt),
    duration_sec: asNumber(row.duration_sec ?? row.duration, 10),
    seed: asSeed(row.seed),
    continuity_source: asContinuitySource(
      row.continuity_source ?? row.continuity,
      rowIndex,
      inputAssetId,
    ),
    input_asset_id: inputAssetId,
    character_ids: asStringList(row.character_ids),
    asset_ids: asStringList(row.asset_ids),
    reference_asset_ids: asStringList(row.reference_asset_ids),
    output_name:
      asText(row.output_name ?? row.label ?? row.name) ||
      `ltx_segment_${String(rowIndex + 1).padStart(3, '0')}`,
    max_attempts: asInteger(row.max_attempts, 2),
    on_error: asText(row.on_error) || 'stop',
  }
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"'
        index += 1
      } else if (char === '"') {
        quoted = false
      } else {
        field += char
      }
      continue
    }

    if (char === '"') {
      quoted = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n') {
      row.push(field.replace(/\r$/, ''))
      if (row.some((value) => value.trim())) rows.push(row)
      row = []
      field = ''
    } else {
      field += char
    }
  }

  if (quoted) throw new Error('CSV import contains an unterminated quoted field.')
  row.push(field.replace(/\r$/, ''))
  if (row.some((value) => value.trim())) rows.push(row)
  return rows
}

function normalizeHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function parseCsvImport(text: string): SequenceSheetRow[] {
  const parsed = parseCsvRows(text)
  if (parsed.length < 2) {
    throw new Error('CSV import requires a header and at least one data row.')
  }
  const headers = parsed[0].map(normalizeHeader)
  if (!headers.includes('prompt') && !headers.includes('video_prompt')) {
    throw new Error('CSV import requires a prompt column.')
  }

  return parsed.slice(1).map((values, rowIndex) => {
    const object: Record<string, unknown> = {}
    headers.forEach((header, columnIndex) => {
      object[header] = values[columnIndex] ?? ''
    })
    return normalizeImportedRow(object, rowIndex)
  })
}

export function parseSequenceSheetImport(text: string, filename = ''): SequenceSheetRow[] {
  const trimmed = text.trim()
  if (!trimmed) throw new Error('Paste CSV or JSON content, or choose a file to import.')

  const parseAsJson =
    filename.toLowerCase().endsWith('.json') || trimmed.startsWith('{') || trimmed.startsWith('[')
  if (!parseAsJson) return parseCsvImport(trimmed)

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (error) {
    throw new Error(
      `JSON import could not be parsed. ${error instanceof Error ? error.message : ''}`,
      { cause: error },
    )
  }

  let rowsValue: unknown = parsed
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const object = parsed as Record<string, unknown>
    const modelFamily = asText(object.model_family)
    if (modelFamily && modelFamily.toLowerCase() !== 'ltx') {
      throw new Error(`Model family "${modelFamily}" is unavailable here. WAN is on hold; import LTX rows only.`)
    }
    rowsValue = object.rows
  }
  if (!Array.isArray(rowsValue) || rowsValue.length === 0) {
    throw new Error('JSON import must be a non-empty row array or an object with a non-empty rows array.')
  }
  return rowsValue.map(normalizeImportedRow)
}

export function createSequenceRow(
  order: number,
  overrides: Partial<SequenceSheetRow> = {},
): SequenceSheetRow {
  const inputAssetId = overrides.input_asset_id ?? null
  const rowId = localRowId()
  return {
    enabled: true,
    scene_id: null,
    subscene_id: null,
    template_key: LTX_SEQUENCE_TEMPLATE_KEY,
    workflow_version: LTX_SEQUENCE_WORKFLOW_VERSION,
    workflow_sha256: LTX_SEQUENCE_WORKFLOW_SHA256,
    model_profile: LTX_SEQUENCE_MODEL_PROFILE,
    mode: 'i2v',
    prompt: '',
    negative_prompt: null,
    duration_sec: 10,
    seed: 'derive',
    continuity_source:
      order === 1
        ? inputAssetId
          ? `asset:${inputAssetId}`
          : 'none'
        : 'previous_last_frame',
    input_asset_id: inputAssetId,
    character_ids: [],
    asset_ids: [],
    reference_asset_ids: [],
    output_name: `ltx_segment_${String(order).padStart(3, '0')}`,
    max_attempts: 2,
    on_error: 'stop',
    ...overrides,
    row_id: rowId,
    order,
  }
}

export function renumberSequenceRows(rows: SequenceSheetRow[]): SequenceSheetRow[] {
  return rows.map((row, index) => ({ ...row, order: index + 1 }))
}

export function buildSequenceSheetRequest(
  projectId: string,
  rows: SequenceSheetRow[],
): SequenceSheetRequest {
  return {
    schema_version: SEQUENCE_SHEET_SCHEMA_VERSION,
    project_id: projectId,
    model_family: 'ltx',
    rows: renumberSequenceRows(rows).map((row) => ({
      ...row,
      negative_prompt: row.negative_prompt ?? '',
    })),
  }
}

export function sequenceSheetSignature(projectId: string, rows: SequenceSheetRow[]): string {
  return JSON.stringify(buildSequenceSheetRequest(projectId, rows))
}

export function validateSequenceRows(rows: SequenceSheetRow[]): LocalSequenceIssue[] {
  const issues: LocalSequenceIssue[] = []
  if (rows.length === 0) {
    return [{ level: 'error', code: 'rows_required', message: 'Add or import at least one row.' }]
  }

  const enabledRows = rows.filter((row) => row.enabled)
  if (enabledRows.length === 0) {
    issues.push({
      level: 'error',
      code: 'enabled_row_required',
      message: 'At least one sequence row must be enabled.',
    })
  }

  const rowIndexById = new Map<string, number>()
  const outputNames = new Set<string>()
  rows.forEach((row, index) => {
    if (!row.row_id.trim()) {
      issues.push({
        level: 'error',
        code: 'row_id_required',
        message: 'Every row requires a stable row_id.',
        row_id: row.row_id,
      })
    } else if (rowIndexById.has(row.row_id)) {
      issues.push({
        level: 'error',
        code: 'duplicate_row_id',
        message: `Duplicate row_id "${row.row_id}".`,
        row_id: row.row_id,
      })
    } else {
      rowIndexById.set(row.row_id, index)
    }

    if (!row.template_key.toLowerCase().includes('ltx') || row.template_key.toLowerCase().includes('wan')) {
      issues.push({
        level: 'error',
        code: 'ltx_template_required',
        message: 'Only an LTX workflow template is allowed. WAN is on hold.',
        row_id: row.row_id,
      })
    }
    if (!row.model_profile.toLowerCase().includes('ltx') || row.model_profile.toLowerCase().includes('wan')) {
      issues.push({
        level: 'error',
        code: 'ltx_model_required',
        message: 'Only the LTX model profile is allowed.',
        row_id: row.row_id,
      })
    }
    if (row.mode !== 'i2v') {
      issues.push({
        level: 'error',
        code: 'i2v_mode_required',
        message: 'Sequence Sheet currently supports LTX I2V only.',
        row_id: row.row_id,
      })
    }

    if (!row.enabled) return
    if (!row.output_name.trim()) {
      issues.push({
        level: 'error',
        code: 'output_name_required',
        message: 'Output name is required.',
        row_id: row.row_id,
      })
    } else if (
      !SAFE_OUTPUT_NAME.test(row.output_name.trim()) ||
      row.output_name.includes('..') ||
      WINDOWS_RESERVED_OUTPUT_NAMES.has(row.output_name.split('.', 1)[0].toUpperCase())
    ) {
      issues.push({
        level: 'error',
        code: 'unsafe_output_name',
        message: 'Output name must be a safe filename stem using letters, digits, dot, underscore, or hyphen.',
        row_id: row.row_id,
      })
    } else if (outputNames.has(row.output_name.trim().toLowerCase())) {
      issues.push({
        level: 'warning',
        code: 'duplicate_output_name',
        message: `Output name "${row.output_name}" is reused.`,
        row_id: row.row_id,
      })
    } else {
      outputNames.add(row.output_name.trim().toLowerCase())
    }

    if (!row.prompt.trim()) {
      issues.push({
        level: 'error',
        code: 'prompt_required',
        message: 'An LTX video prompt is required.',
        row_id: row.row_id,
      })
    }
    if (
      !Number.isFinite(row.duration_sec) ||
      row.duration_sec < SEQUENCE_MIN_DURATION_SEC ||
      row.duration_sec > SEQUENCE_MAX_DURATION_SEC
    ) {
      issues.push({
        level: 'error',
        code: 'duration_out_of_range',
        message: `Duration must be ${SEQUENCE_MIN_DURATION_SEC}–${SEQUENCE_MAX_DURATION_SEC} seconds.`,
        row_id: row.row_id,
      })
    }
    if (
      row.seed !== 'derive' &&
      (!Number.isSafeInteger(row.seed) || row.seed < 0)
    ) {
      issues.push({
        level: 'error',
        code: 'invalid_seed',
        message: 'Seed must be "derive" or a non-negative safe integer.',
        row_id: row.row_id,
      })
    }
    if (
      row.max_attempts != null &&
      (!Number.isInteger(row.max_attempts) || row.max_attempts < 1 || row.max_attempts > 5)
    ) {
      issues.push({
        level: 'error',
        code: 'invalid_max_attempts',
        message: 'Maximum attempts must be an integer from 1 to 5.',
        row_id: row.row_id,
      })
    }
  })

  const enabledIndexes = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => row.enabled)

  enabledIndexes.forEach(({ row, index }, enabledIndex) => {
    const source = row.continuity_source
    if (enabledIndex === 0 && source === 'previous_last_frame') {
      issues.push({
        level: 'error',
        code: 'first_row_previous_frame',
        message: 'The first enabled row cannot use a previous frame.',
        row_id: row.row_id,
      })
    }
    if (source === 'none' && !row.input_asset_id) {
      issues.push({
        level: 'error',
        code: enabledIndex === 0 ? 'first_row_input_required' : 'row_input_required',
        message: 'An LTX I2V row without frame continuity needs an input asset ID.',
        row_id: row.row_id,
      })
    }
    if (source.startsWith('asset:')) {
      const sourceAssetId = source.slice('asset:'.length)
      if (!sourceAssetId || !row.input_asset_id || sourceAssetId !== row.input_asset_id) {
        issues.push({
          level: 'error',
          code: 'asset_continuity_mismatch',
          message: 'Asset continuity must name the same asset as input_asset_id.',
          row_id: row.row_id,
        })
      }
    }
    if (source.startsWith('row:')) {
      const referencedId = source.slice('row:'.length, -':last_frame'.length)
      const referencedIndex = rowIndexById.get(referencedId)
      if (referencedIndex == null) {
        issues.push({
          level: 'error',
          code: 'continuity_row_missing',
          message: `Continuity row "${referencedId}" does not exist.`,
          row_id: row.row_id,
        })
      } else if (referencedIndex >= index) {
        issues.push({
          level: 'error',
          code: 'continuity_row_order',
          message: 'Row continuity can only reference an earlier row.',
          row_id: row.row_id,
        })
      } else if (!rows[referencedIndex]?.enabled) {
        issues.push({
          level: 'error',
          code: 'continuity_row_disabled',
          message: 'Row continuity cannot reference a disabled row.',
          row_id: row.row_id,
        })
      }
    }
  })

  return issues
}

export function remoteSequenceIssues(
  response: SequenceSheetDryRunResponse | null,
): SequenceSheetValidationIssue[] {
  if (!response) return []
  const validation = response.validation
  return [
    ...(response.issues ?? []),
    ...(response.diagnostics ?? []),
    ...(validation?.issues ?? []),
    ...(validation?.errors ?? []),
    ...(validation?.warnings ?? []),
  ]
}

export function dryRunPassed(response: SequenceSheetDryRunResponse): boolean {
  return (
    response.ok !== false &&
    response.valid !== false &&
    response.validation?.valid !== false &&
    response.ready_to_execute === true &&
    response.qualification?.qualified !== false &&
    !remoteSequenceIssues(response).some(
      (issue) => (issue.level ?? issue.severity ?? '').toLowerCase() === 'error',
    )
  )
}
