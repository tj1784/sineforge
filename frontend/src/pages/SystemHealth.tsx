import { useEffect, useState } from 'react'
import { api, type HealthResponse, type RootStatus } from '../api/client'
import { DebugPanel, ErrorNotice } from '../components/Cards'
import { PageHeader } from '../components/Page'
import { StatusCard } from '../components/Cards'

type HealthState = {
  root: RootStatus | null
  backend: HealthResponse | null
  comfy: HealthResponse | null
  runner: HealthResponse | null
  sulphur: HealthResponse | null
  gpu: HealthResponse | null
  ffmpeg: HealthResponse | null
}

function statusOf(response: HealthResponse | null): string {
  return response?.status ? String(response.status) : 'unavailable'
}

export function SystemHealth() {
  const [health, setHealth] = useState<HealthState>({
    root: null,
    backend: null,
    comfy: null,
    runner: null,
    sulphur: null,
    gpu: null,
    ffmpeg: null,
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadHealth() {
      setLoading(true)
      setError(null)
      try {
        const [root, backend, comfy, runner, sulphur, gpu, ffmpeg] = await Promise.all([
          api.rootStatus(),
          api.health(),
          api.comfyHealth(),
          api.comfyApiRunnerHealth(),
          api.sulphurHealth(),
          api.gpuHealth(),
          api.ffmpegHealth(),
        ])
        if (!cancelled) {
          setHealth({ root, backend, comfy, runner, sulphur, gpu, ffmpeg })
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load health endpoints.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadHealth()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="page">
      <PageHeader
        eyebrow="System Health"
        title="Read-only runtime checks"
        description="Health cards call the FastAPI health endpoints and degrade gracefully when services are offline."
      />

      {error ? <ErrorNotice message={error} /> : null}

      <section className="grid four">
        <StatusCard
          title="Root Status"
          status={health.root?.status ?? 'unavailable'}
          detail={health.root?.message ?? 'Backend root status endpoint.'}
          meta="GET /"
        />
        <StatusCard
          title="Backend"
          status={statusOf(health.backend)}
          detail={loading ? 'Checking...' : 'Application health and runtime flags.'}
          meta="GET /health"
        />
        <StatusCard
          title="ComfyUI"
          status={statusOf(health.comfy)}
          detail="Sineforge-owned BlokeyUI engine reachability."
          meta="GET /health/comfy"
        />
        <StatusCard
          title="Native Engine Runner"
          status={statusOf(health.runner)}
          detail="Built-in API-format workflow execution through the owned engine."
          meta="GET /health/comfy-api-runner"
        />
        <StatusCard
          title="Sulphur"
          status={statusOf(health.sulphur)}
          detail="Local script and prompt enhancer model served by LM Studio."
          meta="GET /health/sulphur"
        />
        <StatusCard
          title="GPU"
          status={statusOf(health.gpu)}
          detail="nvidia-smi based telemetry status."
          meta="GET /health/gpu"
        />
        <StatusCard
          title="FFmpeg"
          status={statusOf(health.ffmpeg)}
          detail="ffmpeg and ffprobe binary availability."
          meta="GET /health/ffmpeg"
        />
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>Raw Status Summary</h2>
          <span>Optional debug response</span>
        </div>
        <DebugPanel title="Health payloads" data={health} />
      </section>
    </div>
  )
}
