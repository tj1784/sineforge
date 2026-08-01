import { useEffect, useState } from 'react'
import {
  api,
  type AgentlessWorkflowProfile,
} from '../../api/client'
import { useStudio } from '../StudioState'

const LOCAL_AGENT_LABELS: Record<string, string> = {
  qwen: 'Qwen3 4B Hivemind',
  sulphur: 'Sulphur 2 Base',
  grok: 'Grok',
}

function roleLabel(role: 'flux_anchor' | 'ltx_ingredients_i2v'): string {
  return role === 'flux_anchor'
    ? 'FLUX.2 scene anchor'
    : 'LTX-2.3 Ingredients + I2V'
}

export function AgentlessWorkflowPage({
  blockedFeature,
}: {
  blockedFeature?: string
}) {
  const { projectId, navigate } = useStudio()
  const [profile, setProfile] = useState<AgentlessWorkflowProfile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void api
      .getAgentlessWorkflowProfile(projectId)
      .then((result) => {
        if (!active) return
        setProfile(result)
        setError(null)
      })
      .catch((reason: unknown) => {
        if (!active) return
        setProfile(null)
        setError(
          reason instanceof Error
            ? reason.message
            : 'Agentless workflow policy is unavailable.',
        )
      })
    return () => {
      active = false
    }
  }, [projectId])

  return (
    <>
      <section className="panel" aria-labelledby="agentless-workflow-title">
        <div className="panel-title">
          <div>
            <span className="eyebrow">DETERMINISTIC PROJECT LANE</span>
            <h2 id="agentless-workflow-title">Agentless scene-reset workflow</h2>
            <p>
              Fresh FLUX anchors and LTX Ingredients plus first-frame I2V are
              compiled as independent JSON jobs. Local LM Studio agents may plan
              the project, while hosted/API agents and previous-video frame
              handoffs remain prohibited.
            </p>
          </div>
          <span className="truth-pill unknown">Planning only</span>
        </div>

        {blockedFeature ? (
          <p className="notice warning" role="status">
            <b>{blockedFeature} is unavailable in Agentless Workflow.</b>{' '}
            That Studio surface can bypass the admitted scene-reset contract,
            so this project is held at the deterministic dry-run boundary.
          </p>
        ) : null}
        {error ? <p className="notice error" role="alert">{error}</p> : null}
        {!profile && !error ? (
          <p className="notice" role="status">Loading the persisted Agentless policy…</p>
        ) : null}

        {profile ? (
          <div className="studio-metrics" aria-label="Agentless workflow limits">
            <article><span>Scene manifests</span><strong>1–{profile.max_logical_scenes}</strong></article>
            <article><span>Scene duration</span><strong>{profile.logical_scene_duration_range_sec.join('–')} sec</strong></article>
            <article><span>Standard unit</span><strong>{profile.default_segment_duration_sec} sec</strong></article>
            <article><span>Video timing</span><strong>{profile.default_fps} fps · {profile.default_ten_second_frame_count}f</strong></article>
            <article><span>GPU queue</span><strong>{profile.max_active_gpu_jobs} active</strong></article>
            <article><span>Batch size</span><strong>{profile.batch_size}</strong></article>
            <article>
              <span>Local planning agent</span>
              <strong>{LOCAL_AGENT_LABELS[profile.selected_planning_agent] ?? profile.selected_planning_agent}</strong>
            </article>
          </div>
        ) : null}
      </section>

      {profile ? (
        <div className="split-2">
          <section className="panel" aria-labelledby="agentless-admission-title">
            <div className="panel-title">
              <div>
                <h2 id="agentless-admission-title">Exact workflow admission</h2>
                <p>Both API-format templates must be version- and hash-pinned.</p>
              </div>
              <span className={`truth-pill ${profile.readiness.workflows_admitted ? 'verified' : 'unknown'}`}>
                {profile.readiness.workflows_admitted ? 'Templates admitted' : 'Pins required'}
              </span>
            </div>
            <ul className="kv-list">
              {profile.readiness.admissions.map((admission) => (
                <li key={admission.role}>
                  <span>{roleLabel(admission.role)}</span>
                  <strong>{admission.status.replaceAll('_', ' ')}</strong>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate('workflows')}
            >
              Inspect workflow catalog
            </button>
          </section>

          <section className="panel" aria-labelledby="agentless-safety-title">
            <div className="panel-title">
              <div>
                <h2 id="agentless-safety-title">Non-cumulative guarantees</h2>
                <p>The backend owns the outer loop and keeps every segment isolated.</p>
              </div>
            </div>
            <ul className="feature-list">
              {profile.non_cumulative_guarantees.map((guarantee) => (
                <li key={guarantee}>{guarantee}</li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}

      {profile ? (
        <section className="panel" aria-labelledby="agentless-blockers-title">
          <div className="panel-title">
            <div>
              <h2 id="agentless-blockers-title">Execution boundary</h2>
              <p>
                Dry-run compilation is available at{' '}
                <span className="mono">
                  /projects/{projectId}/agentless-workflow/dry-run
                </span>
                . It does not enqueue ComfyUI work.
              </p>
            </div>
            <span className="truth-pill unknown">Submission disabled</span>
          </div>
          <ul className="gate-list">
            {profile.readiness.blockers.map((blocker) => (
              <li key={`${blocker.code}-${blocker.workflow_role ?? 'lane'}`}>
                <b>{blocker.code}</b>
                <span>{blocker.message}</span>
                <span className="gate-blocking">Blocking</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  )
}
