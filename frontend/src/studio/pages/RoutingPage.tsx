import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  api,
  type LocalModelInventory,
  type PlanningTaskType,
  type ProjectStoryboardSettings,
  type ProviderExecutionMode,
  type ProviderProfile,
  type RuntimeCatalog,
  type TaskProviderAssignment,
} from '../../api/client'
import { formatDate } from '../../components/formatDate'
import { useStudio } from '../StudioState'
import { EmptyState, ErrorState, LoadingState, UnavailableState } from '../components/StateBlocks'

const TASK_PROFILE_MAP: ReadonlyArray<{
  task: PlanningTaskType
  label: string
  logicalProfile: 'Sol' | 'Terra' | 'Luna'
  description: string
}> = [
  { task: 'story_structure', label: 'Story structure', logicalProfile: 'Sol', description: 'Long-form story structure' },
  { task: 'character_bible', label: 'Character profile', logicalProfile: 'Terra', description: 'Structured identity detail' },
  { task: 'chapter_outline', label: 'Chapter outline', logicalProfile: 'Terra', description: 'Chapter-level narrative plan' },
  { task: 'scene_breakdown', label: 'Scene breakdown', logicalProfile: 'Terra', description: 'Narrative continuity and beats' },
  { task: 'shot_list', label: 'Shot list', logicalProfile: 'Luna', description: 'Fast bulk shot planning' },
  { task: 'narration_plan', label: 'Narration plan', logicalProfile: 'Terra', description: 'Narration fit and voice planning' },
  { task: 'prompt_package', label: 'Prompt package', logicalProfile: 'Luna', description: 'Workflow-specific prompt drafting' },
  { task: 'continuity_plan', label: 'Continuity plan', logicalProfile: 'Terra', description: 'Cross-shot continuity review' },
  { task: 'model_recommendation', label: 'Model recommendation', logicalProfile: 'Terra', description: 'Evidence-based model matching' },
  { task: 'production_proposal', label: 'Production proposal', logicalProfile: 'Sol', description: 'Final reviewed proposal synthesis' },
]

type RouteDraft = {
  providerProfileId: string
  enabled: boolean
  rationale: string
}

function evidenceStatus(status: string): string {
  const value = status.toLowerCase()
  if (value === 'available' || value === 'verified' || value === 'ready' || value === 'connected') return 'ready'
  if (value === 'unavailable' || value === 'blocked' || value === 'failed' || value === 'missing') return 'blocked'
  if (value === 'manual' || value === 'review' || value === 'open') return 'review'
  return 'draft'
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function capabilityLabels(profile: ProviderProfile): string {
  const declared =
    profile.capabilities_json.declared_capabilities ?? profile.capabilities_json.capabilities
  return Array.isArray(declared) && declared.length
    ? declared.map(String).join(', ')
    : 'No declared capabilities'
}

export function RoutingPage() {
  const { data, busy, reload, setMessage } = useStudio()
  const [catalog, setCatalog] = useState<RuntimeCatalog | null>(null)
  const [localInventory, setLocalInventory] = useState<LocalModelInventory | null>(null)
  const [profiles, setProfiles] = useState<ProviderProfile[]>([])
  const [assignments, setAssignments] = useState<TaskProviderAssignment[]>([])
  const [settings, setSettings] = useState<ProjectStoryboardSettings | null>(null)
  const [catalogAvailable, setCatalogAvailable] = useState(true)
  const [settingsAvailable, setSettingsAvailable] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState('')
  const [selectedTask, setSelectedTask] = useState<PlanningTaskType>(TASK_PROFILE_MAP[0].task)
  const [modelFilter, setModelFilter] = useState('')
  const [preferLocal, setPreferLocal] = useState(true)
  const [preferHosted, setPreferHosted] = useState(false)
  const [routeDrafts, setRouteDrafts] = useState<Record<string, RouteDraft>>({})
  const [showProfileForm, setShowProfileForm] = useState(false)

  const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId) ?? null

  const load = useCallback(async () => {
    if (!data) return
    setLoading(true)
    setError(null)
    try {
      const [catalogResult, localInventoryResult, profileResult, assignmentResult, settingsResult] = await Promise.all([
        api.runtimeCatalog(),
        api.localModelInventory(),
        api.listProviderProfiles(),
        api.listTaskProviderAssignments(data.story.id),
        api.getSettings(data.story.project_id),
      ])
      setCatalogAvailable(catalogResult != null)
      setCatalog(catalogResult)
      setLocalInventory(localInventoryResult)
      setProfiles(profileResult)
      setAssignments(assignmentResult)
      setRouteDrafts({})
      setSettingsAvailable(settingsResult != null)
      setSettings(settingsResult)
      if (settingsResult) {
        setPreferLocal(settingsResult.prefer_local_providers)
        setPreferHosted(settingsResult.prefer_hosted_providers)
      }
    } catch (err) {
      setError(errorText(err, 'Failed to load routing configuration.'))
    } finally {
      setLoading(false)
    }
  }, [data])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const modelsById = useMemo(
    () => new Map(catalog?.models.map((model) => [model.id, model]) ?? []),
    [catalog],
  )
  const localModelRows = useMemo(() => {
    const query = modelFilter.trim().toLowerCase()
    return Object.entries(localInventory?.categories ?? {})
      .flatMap(([category, names]) => names.map((name) => ({ category, name })))
      .filter(({ category, name }) => !query || `${category} ${name}`.toLowerCase().includes(query))
      .sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name))
  }, [localInventory, modelFilter])

  if (!data) return null

  const resetProfileForm = () => {
    setSelectedProfileId('')
    setShowProfileForm(true)
  }

  const declaredCapabilities = (value: string) =>
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)

  const onSaveProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const providerIdentifier = String(form.get('provider_identifier') ?? '').trim()
    const displayName = String(form.get('display_name') ?? '').trim()
    if (!providerIdentifier || !displayName) return
    setSaving(true)
    setError(null)
    try {
      const payload = {
        display_name: displayName,
        provider_model_id: String(form.get('provider_model_id') ?? '').trim() || null,
        execution_mode: String(form.get('execution_mode') ?? 'disabled') as ProviderExecutionMode,
        privacy_classification: String(form.get('privacy_classification') ?? '').trim() || 'unknown',
        capabilities_json: {
          ...(selectedProfile?.capabilities_json ?? {}),
          declared_capabilities: declaredCapabilities(String(form.get('capabilities') ?? '')),
        },
        capability_source: 'user_declared',
      }
      if (selectedProfileId) {
        await api.updateProviderProfile(selectedProfileId, payload)
        setMessage(`Provider profile “${displayName}” updated. Availability was not inferred or changed.`)
      } else {
        await api.createProviderProfile({
          provider_identifier: providerIdentifier,
          ...payload,
          availability_status: 'unknown',
        })
        setMessage(`Provider profile “${displayName}” created with availability Unknown.`)
      }
      await load()
      setShowProfileForm(false)
    } catch (err) {
      const text = errorText(err, 'Could not save the provider profile.')
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  const onDeleteProfile = async () => {
    if (!selectedProfile) return
    if (!window.confirm(`Delete provider profile “${selectedProfile.display_name}”?`)) return
    setSaving(true)
    setError(null)
    try {
      await api.deleteProviderProfile(selectedProfile.id)
      setSelectedProfileId('')
      setShowProfileForm(false)
      await load()
      setMessage(`Deleted provider profile “${selectedProfile.display_name}”.`)
    } catch (err) {
      const text = errorText(err, 'Could not delete the provider profile.')
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  const draftFor = (task: PlanningTaskType): RouteDraft => {
    const assignment = assignments.find((item) => item.task_type === task)
    return (
      routeDrafts[task] ?? {
        providerProfileId: assignment?.provider_profile_id ?? '',
        enabled: assignment?.enabled ?? true,
        rationale: assignment?.rationale ?? '',
      }
    )
  }

  const updateRouteDraft = (task: PlanningTaskType, patch: Partial<RouteDraft>) => {
    setRouteDrafts((current) => {
      const assignment = assignments.find((item) => item.task_type === task)
      const base = current[task] ?? {
        providerProfileId: assignment?.provider_profile_id ?? '',
        enabled: assignment?.enabled ?? true,
        rationale: assignment?.rationale ?? '',
      }
      return {
        ...current,
        [task]: {
          ...base,
          ...patch,
        },
      }
    })
  }

  const onSaveAssignment = async (task: PlanningTaskType) => {
    const draft = draftFor(task)
    if (!draft.providerProfileId) return
    const existing = assignments.find((assignment) => assignment.task_type === task)
    setSaving(true)
    setError(null)
    try {
      if (existing) {
        await api.updateTaskProviderAssignment(existing.id, {
          provider_profile_id: draft.providerProfileId,
          assignment_mode: 'manual',
          rationale: draft.rationale.trim() || null,
          enabled: draft.enabled,
        })
      } else {
        await api.createTaskProviderAssignment(data.story.id, {
          task_type: task,
          provider_profile_id: draft.providerProfileId,
          assignment_mode: 'manual',
          rationale: draft.rationale.trim() || null,
          enabled: draft.enabled,
          priority: 0,
        })
      }
      await Promise.all([load(), reload()])
      setMessage(
        `Saved the ${TASK_PROFILE_MAP.find((row) => row.task === task)?.label ?? task} provider assignment. Its logical profile remains the displayed default unless a run explicitly overrides it.`,
      )
    } catch (err) {
      const text = errorText(err, 'Could not save the task-provider assignment.')
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  const onDeleteAssignment = async (assignment: TaskProviderAssignment) => {
    setSaving(true)
    setError(null)
    try {
      await api.deleteTaskProviderAssignment(assignment.id)
      await Promise.all([load(), reload()])
      setMessage(`Removed the ${assignment.task_type} provider assignment.`)
    } catch (err) {
      const text = errorText(err, 'Could not delete the task-provider assignment.')
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  const onSavePreferences = async () => {
    if (!settings) return
    if (!preferLocal && !preferHosted) {
      setError('At least one provider privacy preference must remain enabled.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await api.updateSettings(data.story.project_id, {
        shot_duration_min_sec: settings.shot_duration_min_sec,
        shot_duration_max_sec: settings.shot_duration_max_sec,
        continuity_policy_json: settings.continuity_policy_json,
        prompting_policy_json: settings.prompting_policy_json,
        voice_policy_json: settings.voice_policy_json,
        approval_policy_json: settings.approval_policy_json,
        speaking_rate: settings.speaking_rate,
        aspect_ratio: settings.aspect_ratio,
        preview_width: settings.preview_width,
        preview_height: settings.preview_height,
        final_width: settings.final_width,
        final_height: settings.final_height,
        fps: settings.fps,
        captions_enabled: settings.captions_enabled,
        audio_enabled: settings.audio_enabled,
        prefer_hosted_providers: preferHosted,
        prefer_local_providers: preferLocal,
        allow_model_download: settings.allow_model_download,
        allow_rendering: settings.allow_rendering,
        require_voice_consent: settings.require_voice_consent,
        require_production_plan_approval: settings.require_production_plan_approval,
        expected_settings_version: settings.id ? settings.settings_version : undefined,
      })
      if (result == null) {
        setSettingsAvailable(false)
        setMessage('Project routing-preference API is unavailable; no preference was changed.')
        return
      }
      setSettings(result)
      setMessage('Provider privacy preferences saved without probing or contacting a provider.')
    } catch (err) {
      const text = errorText(err, 'Could not save provider privacy preferences.')
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  const selectedRow = TASK_PROFILE_MAP.find((row) => row.task === selectedTask) ?? TASK_PROFILE_MAP[0]
  const selectedDraft = draftFor(selectedRow.task)
  const selectedAssignment = assignments.find((item) => item.task_type === selectedRow.task)
  const selectedAssignmentProfile =
    profiles.find((profile) => profile.id === selectedDraft.providerProfileId) ?? null

  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">MODEL ORCHESTRATION</span>
          <h1>Model routing</h1>
          <p>
            Manage planning provider records and per-story task assignments without storing secrets or claiming a
            connection.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn secondary"
            title="Provider connections and availability are factual records only. This page never sends prompts or credentials."
          >
            Privacy boundary
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void load()}
            disabled={loading || busy || saving}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {loading ? <LoadingState title="Loading routing records…" /> : null}
      {error ? <ErrorState detail={error} onRetry={() => void load()} /> : null}

      <div className="routing-controls">
        <label>
          Privacy preference
          <div className="segmented">
            <button
              type="button"
              className={preferLocal && !preferHosted ? 'active' : ''}
              onClick={() => {
                setPreferLocal(true)
                setPreferHosted(false)
              }}
              disabled={saving || !settings}
            >
              Local only
            </button>
            <button
              type="button"
              className={preferLocal && preferHosted ? 'active' : ''}
              onClick={() => {
                setPreferLocal(true)
                setPreferHosted(true)
              }}
              disabled={saving || !settings}
            >
              Hybrid
            </button>
            <button
              type="button"
              className={!preferLocal && preferHosted ? 'active' : ''}
              onClick={() => {
                setPreferLocal(false)
                setPreferHosted(true)
              }}
              disabled={saving || !settings}
            >
              Hosted allowed
            </button>
          </div>
        </label>
        <label>
          Prefer local
          <select
            value={preferLocal ? 'yes' : 'no'}
            onChange={(event) => setPreferLocal(event.target.value === 'yes')}
            disabled={saving || !settings}
          >
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label>
          Permit hosted
          <select
            value={preferHosted ? 'yes' : 'no'}
            onChange={(event) => setPreferHosted(event.target.value === 'yes')}
            disabled={saving || !settings}
          >
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label>
          Profiles
          <input value={`${profiles.length} configured`} readOnly />
        </label>
        <label>
          Assignments
          <input value={`${assignments.length} saved`} readOnly />
        </label>
        <label>
          Action
          <button
            type="button"
            className="btn primary"
            style={{ width: '100%', marginTop: 5 }}
            onClick={() => void onSavePreferences()}
            disabled={saving || !settings || (!preferLocal && !preferHosted)}
          >
            Save privacy
          </button>
        </label>
      </div>

      {!settingsAvailable && !loading ? (
        <UnavailableState
          title="Project settings unavailable"
          detail="No privacy preference was inferred or changed."
        />
      ) : null}
      {!preferLocal && !preferHosted ? (
        <p className="notice warning">At least one provider class must be permitted for routing.</p>
      ) : null}

      <div className="provider-grid">
        {profiles.map((profile, index) => (
          <button
            key={profile.id}
            type="button"
            onClick={() => {
              setSelectedProfileId(profile.id)
              setShowProfileForm(true)
            }}
          >
            <span className={`provider-logo provider-${index % 4}`} aria-hidden="true">
              {profile.display_name.charAt(0).toUpperCase()}
            </span>
            <span>
              <b>{profile.display_name}</b>
              <small>
                {profile.provider_identifier} · {profile.provider_model_id ?? 'No model'}
              </small>
            </span>
            <span className="status-pill" data-status={evidenceStatus(profile.availability_status)}>
              {profile.availability_status}
            </span>
          </button>
        ))}
        <button type="button" onClick={resetProfileForm}>
          <span className="provider-logo" aria-hidden="true">
            +
          </span>
          <span>
            <b>New profile</b>
            <small>Configuration record only</small>
          </span>
          <span className="status-pill" data-status="draft">
            Create
          </span>
        </button>
      </div>

      {!profiles.length && !loading ? (
        <EmptyState
          title="No provider profiles"
          detail="Create a disabled or manually controlled provider record. Availability begins Unknown."
        />
      ) : null}

      <div className="routing-layout">
        <section className="panel routing-table-panel">
          <header className="panel-head">
            <div>
              <h2>Task-routing matrix</h2>
              <p>Persist a provider profile per task. Sol / Terra / Luna remain logical defaults.</p>
            </div>
          </header>
          <div className="data-table routing-table">
            <div className="table-head">
              <span>Task</span>
              <span>Provider / model</span>
              <span>Mode</span>
              <span>Privacy</span>
              <span>Enabled</span>
              <span>Logical</span>
              <span>Status</span>
            </div>
            {TASK_PROFILE_MAP.map((row) => {
              const draft = draftFor(row.task)
              const profile = profiles.find((item) => item.id === draft.providerProfileId)
              const assignment = assignments.find((item) => item.task_type === row.task)
              return (
                <div
                  key={row.task}
                  role="button"
                  tabIndex={0}
                  className={`data-row ${selectedTask === row.task ? 'selected' : ''}`}
                  onClick={() => setSelectedTask(row.task)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSelectedTask(row.task)
                    }
                  }}
                >
                  <span>
                    <b>{row.label}</b>
                    <small>{row.description}</small>
                  </span>
                  <span onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
                    <select
                      aria-label={`Provider for ${row.label}`}
                      value={draft.providerProfileId}
                      onChange={(event) =>
                        updateRouteDraft(row.task, { providerProfileId: event.target.value })
                      }
                      disabled={saving || !profiles.length}
                    >
                      <option value="">Unassigned</option>
                      {profiles.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.display_name} · {item.availability_status}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label={`Rationale for ${row.label}`}
                      value={draft.rationale}
                      onChange={(event) => updateRouteDraft(row.task, { rationale: event.target.value })}
                      disabled={saving}
                      placeholder={profile?.provider_model_id ?? 'Optional review note'}
                    />
                  </span>
                  <span>
                    <span className="status-pill" data-status={assignment ? 'manual' : 'draft'}>
                      {assignment ? assignment.assignment_mode : 'Unset'}
                    </span>
                  </span>
                  <span>{profile?.privacy_classification ?? '—'}</span>
                  <span onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={(event) => updateRouteDraft(row.task, { enabled: event.target.checked })}
                      disabled={saving}
                      aria-label={`Enable ${row.label} provider assignment`}
                    />
                  </span>
                  <span>
                    <span className="status-pill" data-status="ready">
                      {row.logicalProfile}
                    </span>
                  </span>
                  <span>
                    <span
                      className="status-pill"
                      data-status={
                        assignment
                          ? evidenceStatus(profile?.availability_status ?? 'ready')
                          : 'review'
                      }
                    >
                      {assignment ? profile?.availability_status ?? 'saved' : 'Unassigned'}
                    </span>
                  </span>
                </div>
              )
            })}
          </div>
        </section>

        <aside className="route-detail">
          <header>
            <span className="orchestrator-mark" aria-hidden="true">
              ⚙
            </span>
            <div>
              <span className="eyebrow">ROUTE DETAIL</span>
              <h2>{selectedRow.label}</h2>
            </div>
          </header>
          <dl>
            <div>
              <dt>Logical default</dt>
              <dd>{selectedRow.logicalProfile}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{selectedAssignmentProfile?.display_name ?? 'Unassigned'}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{selectedAssignmentProfile?.provider_model_id ?? '—'}</dd>
            </div>
            <div>
              <dt>Control</dt>
              <dd>{selectedAssignment?.assignment_mode ?? 'Unset'}</dd>
            </div>
            <div>
              <dt>Privacy</dt>
              <dd>{selectedAssignmentProfile?.privacy_classification ?? '—'}</dd>
            </div>
            <div>
              <dt>Availability</dt>
              <dd>
                <span
                  className="status-pill"
                  data-status={evidenceStatus(selectedAssignmentProfile?.availability_status ?? 'draft')}
                >
                  {selectedAssignmentProfile?.availability_status ?? 'unknown'}
                </span>
              </dd>
            </div>
            <div>
              <dt>Enabled</dt>
              <dd>{selectedDraft.enabled ? 'Yes' : 'No'}</dd>
            </div>
          </dl>
          <div className="recommendation">
            <span aria-hidden="true">✧</span>
            <p>
              <b>Why this route</b>
              {selectedDraft.rationale || selectedRow.description}. Logical profile {selectedRow.logicalProfile} is a
              deterministic default; saving writes a manual assignment only.
            </p>
          </div>
          <div className="inline-actions" style={{ marginTop: 10, flexWrap: 'wrap', gap: 7 }}>
            <button
              type="button"
              className="btn primary"
              onClick={() => void onSaveAssignment(selectedRow.task)}
              disabled={saving || !selectedDraft.providerProfileId}
            >
              Save assignment
            </button>
            {selectedAssignment ? (
              <button
                type="button"
                className="btn secondary"
                onClick={() => void onDeleteAssignment(selectedAssignment)}
                disabled={saving}
              >
                Remove
              </button>
            ) : null}
          </div>
          <p className="form-hint" style={{ marginTop: 8 }}>
            No provider validation or health-probe is run from this page; availability remains factual database evidence.
          </p>
        </aside>
      </div>

      {showProfileForm ? (
        <form
          key={selectedProfile?.id ?? 'new'}
          className="panel stack-form form-stack"
          style={{ marginTop: 12 }}
          onSubmit={(event) => void onSaveProfile(event)}
        >
          <header className="panel-head">
            <div>
              <h2>{selectedProfileId ? 'Edit provider profile' : 'Create provider profile'}</h2>
              <p>Availability remains factual backend evidence and is not editable here.</p>
            </div>
            <button type="button" className="btn quiet" onClick={() => setShowProfileForm(false)}>
              Close
            </button>
          </header>
          <div className="form-grid">
            <label>
              Provider identifier
              <input
                name="provider_identifier"
                required
                defaultValue={selectedProfile?.provider_identifier ?? ''}
                disabled={saving}
                readOnly={Boolean(selectedProfileId)}
                placeholder="openai, xai, local_cli…"
              />
            </label>
            <label>
              Display name
              <input
                name="display_name"
                required
                defaultValue={selectedProfile?.display_name ?? ''}
                disabled={saving}
              />
            </label>
          </div>
          <label>
            Provider model ID
            <input
              name="provider_model_id"
              defaultValue={selectedProfile?.provider_model_id ?? ''}
              disabled={saving}
              placeholder="Optional configuration value"
            />
          </label>
          <div className="form-grid">
            <label>
              Execution mode
              <select name="execution_mode" defaultValue={selectedProfile?.execution_mode ?? 'disabled'} disabled={saving}>
                <option value="disabled">Disabled</option>
                <option value="manual">Manual</option>
                <option value="assisted">Assisted</option>
                <option value="automatic">Automatic</option>
              </select>
            </label>
            <label>
              Privacy classification
              <select
                name="privacy_classification"
                defaultValue={selectedProfile?.privacy_classification ?? 'local'}
                disabled={saving}
              >
                <option value="local">Local</option>
                <option value="hosted">Hosted</option>
                <option value="restricted">Restricted</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
          </div>
          <label>
            Declared capabilities
            <input
              name="capabilities"
              defaultValue={
                selectedProfile ? capabilityLabels(selectedProfile).replace('No declared capabilities', '') : 'planning'
              }
              disabled={saving}
              placeholder="Comma-separated, e.g. planning"
            />
          </label>
          {selectedProfile ? (
            <ul className="kv-list">
              <li>
                <span>Capabilities</span>
                <strong>{capabilityLabels(selectedProfile)}</strong>
              </li>
              <li>
                <span>Capability source</span>
                <strong>{selectedProfile.capability_source ?? 'Unknown'}</strong>
              </li>
              <li>
                <span>Capability check</span>
                <strong>
                  {selectedProfile.capabilities_checked_at
                    ? formatDate(selectedProfile.capabilities_checked_at)
                    : 'Never checked'}
                </strong>
              </li>
              <li>
                <span>Health check</span>
                <strong>
                  {selectedProfile.health_checked_at
                    ? formatDate(selectedProfile.health_checked_at)
                    : 'Never checked'}
                </strong>
              </li>
            </ul>
          ) : null}
          <div className="inline-actions">
            <button type="submit" className="btn primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save provider profile'}
            </button>
            {selectedProfile ? (
              <button type="button" className="btn danger" onClick={() => void onDeleteProfile()} disabled={saving}>
                Delete profile
              </button>
            ) : null}
            <button
              type="button"
              className="btn secondary"
              disabled
              title="No provider validation or health-probe endpoint is exposed in Phase 1."
            >
              Validate connection — unavailable
            </button>
          </div>
        </form>
      ) : null}

      <section className="panel" style={{ marginTop: 12 }}>
        <header className="panel-head">
          <div>
            <h2>Installed ComfyUI model lists</h2>
            <p>
              Live read-only inventory from {localInventory?.source_url ?? 'the configured ComfyUI instance'}.
            </p>
          </div>
          <span className="status-pill" data-status={evidenceStatus(localInventory?.status ?? 'unavailable')}>
            {localInventory ? `${localInventory.total_count} files · ${localInventory.status}` : 'Unavailable'}
          </span>
        </header>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <span>Filter installed models and LoRAs</span>
          <input
            value={modelFilter}
            onChange={(event) => setModelFilter(event.target.value)}
            placeholder="Search filename or folder…"
          />
        </label>
        {!localInventory ? (
          <UnavailableState
            title="Live model inventory unavailable"
            detail="Sineforge could not read the configured ComfyUI model-list endpoints."
          />
        ) : null}
        {localInventory && !localModelRows.length ? (
          <EmptyState
            title={modelFilter ? 'No installed files match this filter' : 'No installed model files reported'}
            detail={modelFilter ? 'Clear or change the filter.' : 'ComfyUI returned empty model lists.'}
          />
        ) : null}
        {localModelRows.length ? (
          <div className="data-table">
            <div className="table-head" style={{ gridTemplateColumns: '.45fr 1.55fr' }}>
              <span>ComfyUI folder</span>
              <span>Model filename</span>
            </div>
            {localModelRows.map(({ category, name }) => (
              <div
                key={`${category}:${name}`}
                className="data-row"
                style={{ gridTemplateColumns: '.45fr 1.55fr' }}
              >
                <span>
                  <b>{category.replaceAll('_', ' ')}</b>
                </span>
                <span className="mono">{name}</span>
              </div>
            ))}
          </div>
        ) : null}
        {localInventory && Object.keys(localInventory.errors).length ? (
          <p className="notice warning">
            Some ComfyUI folders could not be read: {Object.keys(localInventory.errors).join(', ')}.
          </p>
        ) : null}
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <header className="panel-head">
          <div>
            <h2>Factual runtime catalog</h2>
            <p>Database evidence only; no hardware or provider probes run from this page.</p>
          </div>
        </header>
        {!catalogAvailable && !loading ? (
          <UnavailableState
            title="Runtime catalog unavailable"
            detail="No model, install, benchmark, or connection claim is inferred."
          />
        ) : null}
        {catalog ? <p className="notice info">{catalog.summary.evidence_note}</p> : null}
        {!loading && catalog && !catalog.model_variants.length ? (
          <EmptyState title="No model variants registered" detail="The runtime catalog contains no model-variant records." />
        ) : null}
        {catalog?.model_variants.length ? (
          <div className="data-table">
            <div className="table-head" style={{ gridTemplateColumns: '1.4fr .5fr .55fr .55fr .7fr .55fr' }}>
              <span>Model / variant</span>
              <span>24 GB</span>
              <span>Path</span>
              <span>Checksum</span>
              <span>Benchmark</span>
              <span>Native voice</span>
            </div>
            {catalog.model_variants.map((variant) => {
              const model = modelsById.get(variant.model_id)
              return (
                <div
                  key={variant.id}
                  className="data-row"
                  style={{ gridTemplateColumns: '1.4fr .5fr .55fr .55fr .7fr .55fr' }}
                >
                  <span>
                    <b>{model ? `${model.family} · ${model.name}` : 'Unknown model'}</b>
                    <small>{variant.variant_name}</small>
                  </span>
                  <span>{variant.compatible_24gb_status || 'unknown'}</span>
                  <span>
                    <span className="status-pill" data-status={evidenceStatus(variant.path_status)}>
                      {variant.path_status}
                    </span>
                  </span>
                  <span>
                    <span className="status-pill" data-status={evidenceStatus(variant.checksum_status)}>
                      {variant.checksum_status}
                    </span>
                  </span>
                  <span>
                    <span className="status-pill" data-status={evidenceStatus(variant.benchmark_status)}>
                      {variant.benchmark_status}
                    </span>
                    {variant.benchmark_run_count ? ` ${variant.benchmark_run_count} run(s)` : ''}
                  </span>
                  <span>{variant.native_voice_capability || 'unknown'}</span>
                </div>
              )
            })}
          </div>
        ) : null}
      </section>
    </div>
  )
}
