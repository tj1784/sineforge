import { useEffect, useState } from 'react'
import { api, type RuntimeStatus } from '../api/client'
import { DebugPanel, ErrorNotice } from '../components/Cards'
import { PageHeader } from '../components/Page'
import { StatusCard } from '../components/Cards'
import { StatusBadge } from '../components/StatusBadge'

const disabledActions = [
  ['Public submit prompt', 'User-facing /prompt submission is not exposed by the API or UI.'],
  ['Standalone ComfyUI UI', 'Sineforge is the only supported operator frontend.'],
  ['Standalone API Runner', 'Workflow execution is built into Sineforge.'],
  ['Arbitrary visual graphs', 'Use curated workflows, editable copies, or API-format JSON.'],
]

export function Runtime() {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadRuntime() {
      setLoading(true)
      setError(null)
      try {
        const status = await api.runtimeStatus()
        if (!cancelled) {
          setRuntime(status)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load runtime status.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadRuntime()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="page">
      <PageHeader
        eyebrow="Runtime"
        title="Local AI runtime"
        description="Sineforge owns the bundled BlokeyUI process, uses ComfyUI as its local engine, and keeps workflow validation, queue controls, and outputs in one application."
      />

      {error ? <ErrorNotice message={error} /> : null}

      <section className="grid three">
        <StatusCard
          title="Bundled Engine"
          status={runtime?.engine.status ?? 'unavailable'}
          detail={loading ? 'Checking...' : runtime?.engine.last_error ?? 'BlokeyUI is owned by Sineforge.'}
          meta={runtime?.engine.pid ? `PID ${runtime.engine.pid}` : 'Managed subprocess'}
        />
        <StatusCard
          title="Sineforge Runner"
          status={String(runtime?.comfy_api_runner.status ?? 'unavailable')}
          detail={
            runtime?.queue.api_runner_available
              ? 'Native execution is ready for validated API-format workflows.'
              : 'The bundled engine is starting or unavailable.'
          }
          meta="No standalone service"
        />
        <StatusCard
          title="Sulphur"
          status={String(runtime?.sulphur.status ?? 'unavailable')}
          detail={
            runtime?.sulphur.model_loaded
              ? `${runtime.sulphur.model_file ?? runtime.sulphur.model_id ?? 'Local model'} is loaded for scripts and prompts.`
              : 'Local Sulphur model is starting or not loaded.'
          }
          meta="LM Studio · 127.0.0.1:1234"
        />
        <StatusCard
          title="object_info"
          status={runtime?.object_info.status ?? 'unavailable'}
          detail={
            runtime?.object_info.available
              ? `${runtime.object_info.class_count ?? 0} classes visible.`
              : 'Not exposed yet or ComfyUI is unavailable.'
          }
          meta="Read-only availability probe"
        />
        <StatusCard
          title="Runtime Boundary"
          status={runtime?.queue.controlled_submission_enabled ? 'ok' : 'disabled'}
          detail="Controlled /prompt submission is available only through the worker/runtime service after readiness checks."
          meta="Public /prompt remains unavailable"
        />
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>Current Phase</h2>
          <span>{runtime?.current_phase ?? 'Loading...'}</span>
        </div>
        <p>
          Backend capability: controlled worker submission{' '}
          {runtime?.queue.controlled_submission_enabled ? 'enabled' : 'disabled'}. User-facing generation{' '}
          {runtime?.queue.public_submission_enabled ? 'enabled' : 'disabled'}. Native Runner{' '}
          {runtime?.queue.api_runner_available ? 'connected' : 'unavailable'}.
        </p>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>Disabled Runtime Actions</h2>
          <span>Intentional gates</span>
        </div>
        <div className="disabled-action-grid">
          {disabledActions.map(([title, detail]) => (
            <article key={title} className="disabled-action">
              <div>
                <strong>{title}</strong>
                <p>{detail}</p>
              </div>
              <StatusBadge status="disabled" />
            </article>
          ))}
        </div>
      </section>

      {runtime ? <DebugPanel title="Runtime status response" data={runtime} /> : null}
    </div>
  )
}
