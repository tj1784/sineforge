import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import {
  api,
  type SulphurProjectWorkspace,
} from '../api/client'
import { LocalPlanningAgentFieldset } from './LocalPlanningAgentFieldset'
import {
  localPlanningAgent,
  type PlanningAgent,
} from '../planningAgents'
import {
  PROJECT_WORKFLOW_LANES,
  type ProjectWorkflowLane,
} from '../workflowLanes'
import '../workflow-lanes.css'
import type { PageId } from './AppShell'

type StudioHomeHeroProps = {
  onNavigateStudio: (page: PageId) => void
  onCreateProject: (
    prompt: string,
    idempotencyKey: string,
    planningAgent: PlanningAgent,
    planningModelId: string | null,
  ) => Promise<SulphurProjectWorkspace>
  onContinueAgentless: (planningAgent: PlanningAgent) => void
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
  onContinueAgentless,
  onNotify,
}: StudioHomeHeroProps) {
  const [prompt, setPrompt] = useState('')
  const [workflowLane, setWorkflowLane] = useState<ProjectWorkflowLane | null>(null)
  const [planningAgent, setPlanningAgent] = useState<PlanningAgent>('qwen')
  const [planningModelId, setPlanningModelId] = useState<string | null>(null)
  const [planningModelLabel, setPlanningModelLabel] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [freeingVram, setFreeingVram] = useState(false)
  const [runtimeMessage, setRuntimeMessage] = useState(
    'ComfyUI and API Runner are available as local tools.',
  )
  const creationAttempt = useRef({
    prompt: '',
    planningAgent: null as PlanningAgent | null,
    planningModelId: null as string | null,
    idempotencyKey: '',
  })

  const idempotencyKeyFor = (
    value: string,
    agent: PlanningAgent,
    modelId: string | null,
  ) => {
    if (
      creationAttempt.current.prompt !== value ||
      creationAttempt.current.planningAgent !== agent ||
      creationAttempt.current.planningModelId !== modelId ||
      !creationAttempt.current.idempotencyKey
    ) {
      creationAttempt.current = {
        prompt: value,
        planningAgent: agent,
        planningModelId: modelId,
        idempotencyKey: `sulphur-project-${crypto.randomUUID()}`,
      }
    }
    return creationAttempt.current.idempotencyKey
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!workflowLane) {
      setCreateError('Choose CineForge Studio Workflow or Agentless Workflow.')
      return
    }
    if (!planningAgent) {
      setCreateError('Choose the local planning agent for this project.')
      return
    }
    if (workflowLane === 'agentless') {
      setCreateError(null)
      onNotify?.(
        `Continuing with ${planningModelLabel ?? localPlanningAgent(planningAgent)?.label ?? 'the local model'} and deterministic scene-reset production`,
      )
      onContinueAgentless(planningAgent)
      return
    }
    const sourceMessage = prompt.trim()
    if (!sourceMessage) {
      setCreateError(
        'Describe the complete project, including the story and total runtime.',
      )
      return
    }
    setCreating(true)
    setCreateError(null)
    const selectedLabel =
      planningModelLabel ?? localPlanningAgent(planningAgent)?.label ?? 'The selected model'
    onNotify?.(`${selectedLabel} is extracting the project brief and building Phase 1`)
    try {
      const workspace = await onCreateProject(
        sourceMessage,
        idempotencyKeyFor(sourceMessage, planningAgent, planningModelId),
        planningAgent,
        planningModelId,
      )
      onNotify?.(
        `${selectedLabel} created ${workspace.project.name}: ${workspace.planned_scene_count} scenes for ${workspace.target_duration_sec} seconds`,
      )
    } catch (error) {
      setCreateError(
        error instanceof Error
          ? error.message
          : 'The selected planning agent could not create the project.',
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

  const freeVram = async () => {
    const confirmed = window.confirm(
      [
        'Free VRAM now?',
        '',
        'This asks ComfyUI to unload cached models and free memory.',
        'It will not run if ComfyUI has queued or active work.',
      ].join('\n'),
    )
    if (!confirmed) return

    setFreeingVram(true)
    setRuntimeMessage('Checking ComfyUI queue before freeing VRAM…')
    try {
      await api.freeNativeApiRunnerMemory()
      setRuntimeMessage('ComfyUI cached models were unloaded and VRAM was freed.')
      onNotify?.('ComfyUI VRAM freed')
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to free VRAM.'
      setRuntimeMessage(message)
      onNotify?.(message)
    } finally {
      setFreeingVram(false)
    }
  }

  const selectedAgent = localPlanningAgent(planningAgent)
  const selectedModelLabel = planningModelLabel ?? selectedAgent?.label ?? 'local model'
  const callToAction =
    workflowLane === 'agentless'
      ? `Continue with ${selectedModelLabel}`
      : creating
        ? `${selectedModelLabel} is creating…`
        : workflowLane === 'cineforge_studio'
          ? planningAgent
            ? `Create with ${selectedModelLabel}`
            : 'Choose an agent'
          : 'Choose a workflow'

  return (
    <section className="studio-home-hero" aria-labelledby="studio-home-title">
      <div className="studio-home-heading">
        <h1 id="studio-home-title">Shape every frame with CineForge</h1>
        <span className="studio-hero-spark" aria-hidden="true">✦</span>
      </div>
      <p>
        Choose how this project should run. CineForge Studio uses the local planning agent
        you select; Agentless blocks hosted agents while combining local planning with
        deterministic JSON production.
      </p>
      <form className="studio-composer" onSubmit={submit} noValidate>
        <fieldset className="workflow-lane-fieldset">
          <legend>
            Project workflow <em>Required</em>
          </legend>
          <div className="workflow-lane-options">
            {PROJECT_WORKFLOW_LANES.map((option) => (
              <label className="workflow-lane-card" key={option.value}>
                <input
                  type="radio"
                  name="homepage-workflow-lane"
                  value={option.value}
                  checked={workflowLane === option.value}
                  required
                  onChange={() => {
                    setWorkflowLane(option.value)
                    setCreateError(null)
                  }}
                />
                <span>
                  <b>{option.label}</b>
                  <small>{option.description}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {workflowLane ? (
          <LocalPlanningAgentFieldset
            name="homepage-planning-agent"
            value={planningAgent}
            onChange={(agent) => {
              setPlanningAgent(agent)
              setCreateError(null)
            }}
            modelId={planningModelId}
            onModelChange={(modelId, agent, displayName) => {
              setPlanningModelId(modelId)
              setPlanningAgent(agent)
              setPlanningModelLabel(displayName ?? null)
              setCreateError(null)
            }}
            policyNote={
              workflowLane === 'agentless'
                ? 'Local LM Studio only. Hosted/API agents remain blocked; production jobs use deterministic JSON manifests.'
                : 'Live LM Studio catalog. Select any installed local model; the list refreshes automatically.'
            }
          />
        ) : null}
        <textarea
          rows={2}
          value={prompt}
          onChange={(event) => {
            setPrompt(event.target.value)
            setCreateError(null)
          }}
          onKeyDown={submitShortcut}
          aria-label="Describe the complete CineForge project"
          placeholder={
            workflowLane === 'agentless'
              ? 'Continue to the full wizard to enter source material and deterministic production settings.'
              : planningAgent
                ? `Tell ${selectedModelLabel} the complete story, total length, audience, style, format, and every requirement…`
                : 'Choose a Studio planning agent, then describe the complete project…'
          }
          disabled={creating || workflowLane === 'agentless'}
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
            {workflowLane === 'agentless'
              ? `${selectedModelLabel} · local only · deterministic JSON production`
              : planningAgent
                ? `${selectedModelLabel} · LM Studio · project + script`
                : 'Choose a local planning agent'}
          </span>
          <button
            className="studio-build-button"
            type="submit"
            disabled={creating}
            aria-label={callToAction}
          >
            <span>✦</span>
            <span>{callToAction}</span>
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
        <button type="button" onClick={() => void freeVram()} disabled={freeingVram || restarting}>
          {freeingVram ? '♨ Freeing VRAM…' : '♨ Free VRAM'}
        </button>
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
