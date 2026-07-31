import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type OrchestrationRunDetail,
  type StoryboardProposal,
} from '../../api/client'
import { useStudio } from '../StudioState'
import { countScenes, countShots, formatDuration } from '../utils'
import { ProductionPhases } from '../components/ProductionPhases'
import { formatPlanningRoute } from '../planningRouteDisplay'

export function OverviewPage() {
  const { data, readiness, approvePlan, busy, backendStatus, navigate } = useStudio()
  const [approver, setApprover] = useState('Producer')
  const [currentRun, setCurrentRun] = useState<OrchestrationRunDetail | null>(null)
  const [currentProposal, setCurrentProposal] = useState<StoryboardProposal | null>(null)
  const [planningError, setPlanningError] = useState<string | null>(null)

  const loadPlanningSummary = useCallback(async () => {
    if (!data) return
    setPlanningError(null)
    try {
      const [runs, proposals] = await Promise.all([
        api.listOrchestrationRuns(data.story.id),
        api.listStoryProposals(data.story.id),
      ])
      setCurrentRun(runs[0] ? await api.getOrchestrationRun(runs[0].id) : null)
      setCurrentProposal(proposals[0] ?? null)
    } catch (error) {
      setPlanningError(
        backendStatus === 'ok'
          ? 'Planning summary API is unavailable for this local demo story. Backend health is OK.'
          : error instanceof Error ? error.message : 'Planning status is unavailable.',
      )
    }
  }, [backendStatus, data])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPlanningSummary(), 0)
    return () => window.clearTimeout(timer)
  }, [loadPlanningSummary])

  if (!data) return null

  const metrics: Array<[string, string | number]> = [
    ['Chapters', data.chapters.length],
    ['Scenes', countScenes(data.chapters)],
    ['Shots', countShots(data.chapters)],
    ['Characters', data.characters.length],
    ['Voice profiles', data.voices.length],
    ['Readiness', readiness ? (readiness.ready ? 'Ready' : 'Review') : 'Unknown'],
  ]

  const planned = readiness?.planned_duration_sec ?? 0
  const target = readiness?.target_duration_sec ?? data.story.target_duration_sec
  const ratio = target > 0 ? Math.min(100, Math.round((planned / target) * 100)) : 0
  const blocking = readiness?.reasons.filter((reason) => reason.blocking) ?? []
  const canApprove = Boolean(readiness?.ready) && !busy
  const currentStep = currentRun?.steps.find((step) => step.status === 'running') ??
    currentRun?.steps.find((step) => step.sequence_index === currentRun.current_step) ??
    currentRun?.steps.at(-1)
  const completedSteps = currentRun?.steps.filter((step) => step.status === 'completed').length ?? 0
  const routing = currentRun?.routing_snapshot_json

  return (
    <>
      <ProductionPhases
        storyId={data.story.id}
        projectId={data.story.project_id}
        data={data}
        onNavigate={navigate}
      />

      <details className="backend-diagnostics">
        <summary>
          <div><span className="eyebrow">LIVE BACKEND</span><b>Planning diagnostics</b><small>Expand to inspect runs, drafts, routes, and readiness.</small></div>
          <span className={`truth-pill ${backendStatus === 'ok' ? 'verified' : 'unknown'}`}>{backendStatus}</span>
        </summary>
        <div className="backend-diagnostics-content">
      <div className="studio-metrics" aria-label="Planning metrics">
        {metrics.map(([label, value]) => (
          <article key={String(label)}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>

      <div className="split-2">
        <div className="panel">
          <div className="panel-title">
            <div>
              <h2>Duration alignment</h2>
              <p>Values come from the readiness endpoint, not client estimates.</p>
            </div>
            <span className="truth-pill">{backendStatus}</span>
          </div>
          <ul className="kv-list">
            <li>
              <span>Planned</span>
              <strong>{formatDuration(planned)}</strong>
            </li>
            <li>
              <span>Target</span>
              <strong>{formatDuration(target)}</strong>
            </li>
            <li>
              <span>Discrepancy</span>
              <strong>
                {readiness ? `${readiness.discrepancy_sec >= 0 ? '+' : ''}${readiness.discrepancy_sec}s` : '—'}
              </strong>
            </li>
            <li>
              <span>Approval state</span>
              <strong>{data.story.approval_state}</strong>
            </li>
          </ul>
          <div className="progress-bar" aria-hidden="true">
            <span style={{ width: `${ratio}%` }} />
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <div>
              <h2>Safety posture</h2>
              <p>Approval creates an immutable storyboard version only.</p>
            </div>
          </div>
          <ul className="feature-list">
            <li>No Timeline Slot</li>
            <li>No Clip Iteration</li>
            <li>No queue job</li>
            <li>No ComfyUI submission</li>
            <li>No FFmpeg job</li>
            <li>No voice clone / TTS batch</li>
          </ul>
        </div>
      </div>

      <section className="panel" aria-labelledby="overview-planning-status">
        <div className="panel-title">
          <div>
            <h2 id="overview-planning-status">Planning orchestration</h2>
            <p>Live run, route, step, and proposal state from the backend.</p>
          </div>
          <button
            type="button"
            className="primary-button touch-target"
            onClick={() => navigate('story')}
          >
            {currentProposal ? 'Open planning draft' : currentRun ? 'Open run details' : 'Generate planning draft'}
          </button>
        </div>
        {planningError ? <p className="notice warning">{planningError}</p> : null}
        <div className="split-2">
          <ul className="kv-list">
            <li><span>Current run</span><strong>{currentRun?.status ?? 'No run'}</strong></li>
            <li><span>Current step</span><strong>{currentStep?.task_type ?? '—'}</strong></li>
            <li><span>Logical model</span><strong>{currentStep?.logical_model ?? '—'}</strong></li>
            <li><span>Resolved route</span><strong>{currentStep ? formatPlanningRoute(currentStep) : '—'}</strong></li>
            <li><span>Progress</span><strong>{currentRun ? `${completedSteps}/${currentRun.steps.length} steps` : '—'}</strong></li>
          </ul>
          <ul className="kv-list">
            <li><span>Routing mode</span><strong>{String(routing?.mode ?? 'Not configured')}</strong></li>
            <li><span>Local providers</span><strong>{routing ? (routing.prefer_local_providers ? 'Permitted' : 'Disabled') : '—'}</strong></li>
            <li><span>Hosted providers</span><strong>{routing ? (routing.prefer_hosted_providers ? 'Permitted' : 'Disabled') : '—'}</strong></li>
            <li><span>Repairs</span><strong>{currentRun ? `${currentRun.repair_used}/${currentRun.repair_budget}` : '—'}</strong></li>
            <li><span>Latest proposal</span><strong>{currentProposal?.status ?? 'None'}</strong></li>
          </ul>
        </div>
        {currentRun?.failure_message ? <p className="notice error">{currentRun.failure_message}</p> : null}
      </section>

      <div className="panel">
        <div className="panel-title">
          <div>
            <h2>Backend readiness checks</h2>
            <p>
              Gate truth is returned by <span className="mono">/storyboard/stories/:id/readiness</span>.
              The UI never hard-codes ready/not-ready.
            </p>
          </div>
          <span className={`truth-pill ${readiness?.ready ? 'verified' : 'unknown'}`}>
            {readiness ? (readiness.ready ? 'Server: ready' : 'Server: not ready') : 'Server: unknown'}
          </span>
        </div>

        <ul className="gate-list">
          {readiness?.reasons?.length ? (
            readiness.reasons.map((reason) => (
              <li key={`${reason.code}-${reason.entity_id ?? 'none'}-${reason.message}`}>
                <b>{reason.code}</b>
                <span>{reason.message}</span>
                <span className={reason.blocking ? 'gate-blocking' : 'gate-info'}>
                  {reason.blocking ? 'Blocking' : 'Info'}
                </span>
              </li>
            ))
          ) : readiness?.ready ? (
            <li>
              <b>ready</b>
              <span>All current backend readiness checks pass.</span>
              <span className="gate-info">Pass</span>
            </li>
          ) : (
            <li>
              <b>pending</b>
              <span>Readiness reasons have not been returned yet.</span>
              <span className="gate-blocking">Unknown</span>
            </li>
          )}
        </ul>

        <div className="stack-form" style={{ maxWidth: 420 }}>
          <label>
            Approved by
            <input
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
              disabled={busy}
              autoComplete="name"
            />
          </label>
          <button
            type="button"
            className="primary-button touch-target"
            disabled={!canApprove || !approver.trim()}
            title={
              readiness?.ready
                ? 'Approve production plan on the server'
                : blocking.length
                  ? `Blocked by ${blocking.length} readiness gate(s)`
                  : 'Server has not marked this plan ready'
            }
            onClick={() => void approvePlan(approver.trim())}
          >
            Approve production plan
          </button>
          {!readiness?.ready ? (
            <p className="form-hint">
              Approve stays disabled until the backend reports <code>ready: true</code>.
            </p>
          ) : null}
        </div>
      </div>
        </div>
      </details>
    </>
  )
}
