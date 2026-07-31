import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  api,
  type ProjectStoryboardSettings,
  type ProjectStoryboardSettingsUpdate,
} from '../../api/client'
import { useStudio } from '../StudioState'
import { ErrorState, LoadingState, UnavailableState } from '../components/StateBlocks'

const DEFAULT_DRAFT: ProjectStoryboardSettingsUpdate = {
  shot_duration_min_sec: 6,
  shot_duration_max_sec: 12,
  continuity_policy_json: {
    require_starting_image_when_flagged: true,
    allow_cross_scene_continuity: true,
  },
  prompting_policy_json: {
    require_visual_description: false,
    require_story_purpose: false,
  },
  voice_policy_json: {
    allow_placeholder_for_approval: true,
    allow_manual_for_approval: true,
    require_consent_when_required: true,
    block_unresolved_provider_voices: false,
  },
  approval_policy_json: {
    require_exact_duration: true,
    require_at_least_one_chapter: true,
    require_at_least_one_scene: true,
    require_at_least_one_shot: true,
    require_narration_or_exception: true,
    block_on_shot_blocked: true,
  },
  speaking_rate: 1,
  aspect_ratio: '16:9',
  preview_width: 1280,
  preview_height: 720,
  final_width: 1920,
  final_height: 1080,
  fps: 24,
  captions_enabled: true,
  audio_enabled: true,
  production_profile_key: 'ltx_base@1',
  production_profile_snapshot_json: {},
  stitch_stage: 'phase7_before_audio',
  prefer_hosted_providers: false,
  prefer_local_providers: true,
  allow_model_download: true,
  allow_rendering: true,
  require_voice_consent: true,
  require_production_plan_approval: false,
}

function editableSettings(settings: ProjectStoryboardSettings): ProjectStoryboardSettingsUpdate {
  return {
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
    production_profile_key: settings.production_profile_key,
    production_profile_snapshot_json: settings.production_profile_snapshot_json,
    stitch_stage: settings.stitch_stage,
    prefer_hosted_providers: settings.prefer_hosted_providers,
    prefer_local_providers: settings.prefer_local_providers,
    allow_model_download: settings.allow_model_download,
    allow_rendering: settings.allow_rendering,
    require_voice_consent: settings.require_voice_consent,
    require_production_plan_approval: settings.require_production_plan_approval,
  }
}

export function SettingsPage() {
  const { data, busy, setMessage, backendStatus, workflowLane } = useStudio()
  const [settings, setSettings] = useState<ProjectStoryboardSettings | null>(null)
  const [available, setAvailable] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<ProjectStoryboardSettingsUpdate>(DEFAULT_DRAFT)

  const load = useCallback(async () => {
    if (!data) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.getSettings(data.story.project_id)
      if (result == null) {
        setAvailable(false)
        setSettings(null)
        setDraft(DEFAULT_DRAFT)
      } else {
        setAvailable(true)
        setSettings(result)
        setDraft(editableSettings(result))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings.')
    } finally {
      setLoading(false)
    }
  }, [data])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  if (!data) return null

  const onSave = async (event: FormEvent) => {
    event.preventDefault()
    if (!available) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateSettings(data.story.project_id, {
        ...draft,
        expected_settings_version: settings?.id ? settings.settings_version : undefined,
        allow_model_download: Boolean(draft.allow_model_download),
        allow_rendering: Boolean(draft.allow_rendering),
      })
      if (!updated) {
        setAvailable(false)
        setMessage('Project storyboard settings API is unavailable on this backend.')
        return
      }
      setSettings(updated)
      setDraft(editableSettings(updated))
      const bits = [
        updated.allow_model_download ? 'model/LoRA download on' : 'model/LoRA download off',
        updated.allow_rendering ? 'rendering on' : 'rendering off',
      ]
      setMessage(`Project storyboard settings saved (${bits.join(', ')}).`)
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Could not save settings.'
      setError(text)
      setMessage(text)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <LoadingState title="Loading project settings…" detail="Fetching project-scoped policy configuration." />
  }

  if (!available) {
    return (
      <>
        <UnavailableState
          title="Settings API unavailable"
          detail="This backend does not currently expose the project storyboard-settings GET/PUT contract. No local fallback is presented as persisted policy."
        />
        <div className="panel" style={{ marginTop: 14 }}>
          <h2>Read-only story context</h2>
          <ul className="kv-list">
            <li><span>Project</span><strong className="mono">{data.story.project_id}</strong></li>
            <li><span>Story</span><strong>{data.story.title}</strong></li>
            <li><span>Target duration</span><strong>{data.story.target_duration_sec}s</strong></li>
            <li><span>Backend</span><strong>{backendStatus}</strong></li>
          </ul>
        </div>
      </>
    )
  }

  const savingDisabled = saving || busy
  const agentlessPolicyLocked = workflowLane === 'agentless'
  const laneLockedDisabled = savingDisabled || agentlessPolicyLocked

  return (
    <form className="panel stack-form" style={{ maxWidth: 760 }} onSubmit={(event) => void onSave(event)}>
      <div className="panel-title">
        <div>
          <h2>Project storyboard settings</h2>
          <p>
            Project <span className="mono">{data.story.project_id}</span> · settings version{' '}
            {settings?.settings_version ?? 'new'}.
          </p>
        </div>
        <button type="button" className="ghost-button touch-target" onClick={() => void load()} disabled={savingDisabled}>
          Refresh
        </button>
      </div>

      {error ? <ErrorState detail={error} onRetry={() => void load()} /> : null}
      {agentlessPolicyLocked ? (
        <p className="notice" role="status">
          Agentless policy locks LTX Base v2, 3–10 second generation units,
          24 fps, model downloads off, and rendering off until the
          project-scoped execution boundary is implemented.
        </p>
      ) : null}

      <div className="split-2">
        <label>
          Video production profile
          <select
            value={draft.production_profile_key}
            onChange={(event) => setDraft({
              ...draft,
              production_profile_key: event.target.value as ProjectStoryboardSettingsUpdate['production_profile_key'],
            })}
            disabled={laneLockedDisabled}
          >
            <option value="ltx_base@1">LTX Base v1 · qualified compatibility</option>
            <option value="ltx_base@2">LTX Base v2 · 8–15 second Sequence Sheet</option>
            <option value="wan_base@1" disabled>WAN Base v1 · on hold after failed dry run</option>
          </select>
          <small>
            {agentlessPolicyLocked
              ? 'Agentless scenes compile into independently anchored LTX-2.3 units; exact FLUX and LTX workflow admission is still required.'
              : draft.production_profile_key === 'wan_base@1'
              ? 'WAN remains readable for existing projects, but it is disabled and cannot execute while on hold.'
              : draft.production_profile_key === 'ltx_base@2'
                ? 'One LTX request per 8–15 second row. Execution requires the exact static API workflow to pass qualification.'
                : 'Preserves the existing qualified 6–10 second LTX compatibility profile.'}
          </small>
        </label>
        <label>
          Stitch stage
          <select
            value={draft.stitch_stage}
            onChange={(event) => setDraft({
              ...draft,
              stitch_stage: event.target.value as ProjectStoryboardSettingsUpdate['stitch_stage'],
            })}
            disabled={savingDisabled}
          >
            <option value="phase7_before_audio">Phase 7 · stitch before audio</option>
            <option value="phase8_before_foley">Phase 8 · defer stitch before Foley</option>
          </select>
          <small>Phase 7 picture lock remains the required immutable input to final audio delivery.</small>
        </label>
      </div>

      <div className="split-2">
        <label>
          Shot duration min (sec)
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={draft.shot_duration_min_sec}
            onChange={(event) => setDraft({ ...draft, shot_duration_min_sec: Number(event.target.value) })}
            disabled={laneLockedDisabled}
          />
        </label>
        <label>
          Shot duration max (sec)
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={draft.shot_duration_max_sec}
            onChange={(event) => setDraft({ ...draft, shot_duration_max_sec: Number(event.target.value) })}
            disabled={laneLockedDisabled}
          />
        </label>
      </div>

      <div className="split-2">
        <label>
          Aspect ratio
          <select
            value={draft.aspect_ratio}
            onChange={(event) => setDraft({ ...draft, aspect_ratio: event.target.value })}
            disabled={savingDisabled}
          >
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
            <option value="1:1">1:1</option>
            <option value="2.39:1">2.39:1</option>
          </select>
        </label>
        <label>
          Frames per second
          <input
            type="number"
            min={1}
            step={1}
            value={draft.fps}
            onChange={(event) => setDraft({ ...draft, fps: Number(event.target.value) })}
            disabled={laneLockedDisabled}
          />
        </label>
      </div>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={Boolean(draft.approval_policy_json.require_exact_duration)}
          onChange={(event) => setDraft({
            ...draft,
            approval_policy_json: {
              ...draft.approval_policy_json,
              require_exact_duration: event.target.checked,
            },
          })}
          disabled={savingDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>Require exact reconciled story duration</span>
      </label>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={Boolean(draft.continuity_policy_json.require_starting_image_when_flagged)}
          onChange={(event) => setDraft({
            ...draft,
            continuity_policy_json: {
              ...draft.continuity_policy_json,
              require_starting_image_when_flagged: event.target.checked,
            },
          })}
          disabled={savingDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>Require a starting image when a shot is flagged</span>
      </label>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={draft.require_voice_consent}
          onChange={(event) => setDraft({ ...draft, require_voice_consent: event.target.checked })}
          disabled={savingDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>Require voice consent</span>
      </label>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={draft.require_production_plan_approval}
          onChange={(event) => setDraft({ ...draft, require_production_plan_approval: event.target.checked })}
          disabled={savingDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>Require production-plan approval</span>
      </label>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={Boolean(draft.allow_model_download)}
          onChange={(event) => setDraft({ ...draft, allow_model_download: event.target.checked })}
          disabled={laneLockedDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>
          Allow model and LoRA downloads (checkpoints, adapters, weights for better video quality)
        </span>
      </label>

      <label style={{ gridTemplateColumns: 'auto 1fr', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={Boolean(draft.allow_rendering)}
          onChange={(event) => setDraft({ ...draft, allow_rendering: event.target.checked })}
          disabled={laneLockedDisabled}
          style={{ width: 20, height: 20, minHeight: 20 }}
        />
        <span>Allow rendering / video generation jobs when the runtime worker is enabled</span>
      </label>

      <div className="inline-actions">
        <button type="submit" className="primary-button touch-target" disabled={savingDisabled}>
          {saving ? 'Saving…' : 'Save settings'}
        </button>
        <span className="truth-pill">Server-backed · revision-aware PUT</span>
      </div>

      <p className="form-hint">
        {agentlessPolicyLocked
          ? 'The locked controls are enforced again by the backend on every settings update.'
          : 'Model/LoRA download and rendering flags are project policy. Downloads still require a configured runtime and worker; enabling the flags does not auto-fetch weights by itself.'}
      </p>
    </form>
  )
}
