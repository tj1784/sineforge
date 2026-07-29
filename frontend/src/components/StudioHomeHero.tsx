import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api, type SulphurProjectWorkspace } from '../api/client'
import type { PageId } from './AppShell'

type StudioHomeHeroProps = {
  onNavigateStudio: (page: PageId) => void
  onCreateProject: (
    prompt: string,
    idempotencyKey: string,
  ) => Promise<SulphurProjectWorkspace>
  onNotify?: (message: string) => void
}

const quickLinks: { page: PageId; label: string; icon: string }[] = [
  { page: 'storyboard', label: 'Storyboard', icon: '▤' },
  { page: 'characters', label: 'Characters', icon: '♙' },
  { page: 'images', label: 'Starting images', icon: '▧' },
  { page: 'workflows', label: 'Workflows', icon: '◇' },
  { page: 'overview', label: 'All seven phases', icon: '✦' },
]

const RESTART_POLL_INTERVAL_MS = 2_000
const RESTART_POLL_LIMIT = 90

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))
}

export function StudioHomeHero({
  onNavigateStudio,
  onCreateProject,
  onNotify,
}: StudioHomeHeroProps) {
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [runtimeMessage, setRuntimeMessage] = useState(
    'ComfyUI and API Runner are available as local tools.',
  )
  const creationAttempt = useRef({ prompt: '', idempotencyKey: '' })

  const idempotencyKeyFor = (value: string) => {
    if (
      creationAttempt.current.prompt !== value ||
      !creationAttempt.current.idempotencyKey
    ) {
      creationAttempt.current = {
        prompt: value,
        idempotencyKey: `sulphur-project-${crypto.randomUUID()}`,
      }
    }
    return creationAttempt.current.idempotencyKey
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const sourceMessage = prompt.trim()
    if (!sourceMessage) {
      setCreateError(
        'Describe the complete project for Sulphur, including the story and total runtime.',
      )
      return
    }
    setCreating(true)
    setCreateError(null)
    onNotify?.('Sulphur is extracting the project brief and building Phase 1')
    try {
      const workspace = await onCreateProject(
        sourceMessage,
        idempotencyKeyFor(sourceMessage),
      )
      onNotify?.(
        `Sulphur created ${workspace.project.name}: ${workspace.planned_scene_count} scenes for ${workspace.target_duration_sec} seconds`,
      )
    } catch (error) {
      setCreateError(
        error instanceof Error
          ? error.message
          : 'Sulphur could not create the project.',
      )
    } finally {
      setCreating(false)
    }
  }

  const submitShortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  const restartComfyUi = async () => {
    setRestarting(true)
    setRuntimeMessage('Scheduling the ComfyUI restart through API Runner…')
    try {
      const request = await api.restartComfyUi()
      setRuntimeMessage(request.message)
      for (let attempt = 0; attempt < RESTART_POLL_LIMIT; attempt += 1) {
        const result = await api.comfyRestartStatus(request.restart_id)
        setRuntimeMessage(result.message || `ComfyUI restart: ${result.status}`)
        if (result.complete) {
          setRuntimeMessage('ComfyUI restarted successfully with CUDA device 0.')
          onNotify?.('ComfyUI restarted successfully')
          return
        }
        if (result.failed) {
          throw new Error(result.message || 'ComfyUI restart failed.')
        }
        await wait(RESTART_POLL_INTERVAL_MS)
      }
      throw new Error('ComfyUI restart is taking longer than three minutes.')
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to restart ComfyUI.'
      setRuntimeMessage(message)
      onNotify?.(message)
    } finally {
      setRestarting(false)
    }
  }

  return (
    <section className="studio-home-hero" aria-labelledby="studio-home-title">
      <div className="studio-home-heading">
        <h1 id="studio-home-title">Shape every frame with CineForge</h1>
        <span className="studio-hero-spark" aria-hidden="true">✦</span>
      </div>
      <p>
        Give Sulphur one complete creative brief. It will build the project, script, timing,
        and eight-second scene plan in one controlled local workflow.
      </p>
      <form className="studio-composer" onSubmit={submit}>
        <textarea
          rows={2}
          value={prompt}
          onChange={(event) => {
            setPrompt(event.target.value)
            setCreateError(null)
          }}
          onKeyDown={submitShortcut}
          aria-label="Describe the complete CineForge project for Sulphur"
          placeholder="Tell Sulphur the complete story, total length, audience, style, format, and every requirement…"
          disabled={creating}
          maxLength={24_000}
        />
        <footer>
          <div className="studio-composer-tools">
            <button type="button" onClick={() => onNavigateStudio('voices')} aria-label="Open voice workspace" title="Open voice workspace">
              ♬
            </button>
            <button type="button" onClick={() => onNavigateStudio('images')} aria-label="Open starting images" title="Open starting images">
              ＋
            </button>
          </div>
          <span className="studio-local-note">
            <i />
            Sulphur · local Q8_0 · project + script
          </span>
          <button className="studio-build-button" type="submit" disabled={creating}>
            <span>✦</span>
            <span>{creating ? 'Sulphur is creating…' : 'Create complete project'}</span>
            <kbd>Ctrl</kbd>
            <kbd>↵</kbd>
          </button>
        </footer>
        {createError ? (
          <p className="studio-composer-error" role="alert">{createError}</p>
        ) : null}
      </form>
      <div className="studio-runtime-actions" aria-label="Local AI runtime controls">
        <span className="studio-runtime-status" role="status" aria-live="polite">
          <i />
          {runtimeMessage}
        </span>
        <a href="http://127.0.0.1:8022" target="_blank" rel="noreferrer">
          ◇ Open API Runner
        </a>
        <a href="http://127.0.0.1:8888" target="_blank" rel="noreferrer">
          ▧ Open ComfyUI
        </a>
        <button type="button" onClick={() => void restartComfyUi()} disabled={restarting}>
          {restarting ? '↻ Restarting ComfyUI…' : '↻ Restart ComfyUI'}
        </button>
      </div>
      <nav className="studio-suggestion-row" aria-label="Production workspace shortcuts">
        {quickLinks.map((item) => (
          <button
            key={item.page}
            type="button"
            onClick={() => {
              onNavigateStudio(item.page)
              onNotify?.(`Opening ${item.label}`)
            }}
          >
            <span aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </section>
  )
}
