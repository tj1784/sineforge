import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type LMStudioModel,
  type LMStudioModelCatalog,
} from '../api/client'
import {
  LOCAL_PLANNING_AGENTS,
  type PlanningAgent,
} from '../planningAgents'

type LocalPlanningAgentFieldsetProps = {
  name: string
  value: PlanningAgent | null
  onChange: (agent: PlanningAgent) => void
  modelId?: string | null
  onModelChange?: (
    modelId: string | null,
    agent: PlanningAgent,
    displayName?: string,
  ) => void
  policyNote?: string
}

const MODEL_REFRESH_INTERVAL_MS = 10_000

function inferredAgent(model: Pick<LMStudioModel, 'model_id' | 'key' | 'display_name'>): PlanningAgent {
  const haystack = `${model.model_id} ${model.key} ${model.display_name}`.toLowerCase()
  if (haystack.includes('sulphur')) return 'sulphur'
  if (haystack.includes('grok') || haystack.includes('xai')) return 'grok'
  return 'qwen'
}

function modelDetails(model: LMStudioModel) {
  return [
    model.loaded ? 'Loaded in LM Studio' : 'Available in LM Studio',
    model.params_string,
    model.quantization,
    model.context_length ? `${model.context_length.toLocaleString()} context` : null,
  ].filter(Boolean).join(' · ')
}

export function LocalPlanningAgentFieldset({
  name,
  value,
  onChange,
  modelId,
  onModelChange,
  policyNote,
}: LocalPlanningAgentFieldsetProps) {
  const [catalog, setCatalog] = useState<LMStudioModelCatalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [changingModelId, setChangingModelId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const onChangeRef = useRef(onChange)
  const onModelChangeRef = useRef(onModelChange)

  useEffect(() => {
    onChangeRef.current = onChange
    onModelChangeRef.current = onModelChange
  }, [onChange, onModelChange])

  const refresh = useCallback(async (announceSelection = false) => {
    try {
      const nextCatalog = await api.listLmStudioModels()
      setCatalog(nextCatalog)
      setError(nextCatalog.error)
      if (announceSelection) {
        const active = nextCatalog.models.find(
          (model) =>
            model.selected ||
            model.model_id === nextCatalog.active_model_id ||
            model.loaded_instance_ids.includes(nextCatalog.active_model_id),
        )
        if (active) {
          const agent = inferredAgent(active)
          onChangeRef.current(agent)
          onModelChangeRef.current?.(
            nextCatalog.active_model_id,
            agent,
            active.display_name,
          )
        }
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'The LM Studio model list is unavailable.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => void refresh(true), 0)
    const timer = window.setInterval(() => void refresh(), MODEL_REFRESH_INTERVAL_MS)
    const onFocus = () => void refresh(true)
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearTimeout(initialRefresh)
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
    }
  }, [refresh])

  const selectedModelId = modelId ?? catalog?.active_model_id ?? null
  const liveModels = useMemo(
    () => catalog?.models.filter((model) => model.installed) ?? [],
    [catalog],
  )

  const selectModel = async (model: LMStudioModel) => {
    const agent = inferredAgent(model)
    setChangingModelId(model.model_id)
    setError(null)
    try {
      const activation = await api.activateLmStudioModel(model.model_id)
      onChange(agent)
      onModelChange?.(
        activation.active_model_id,
        agent,
        activation.model.display_name,
      )
      await refresh()
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'LM Studio could not load the selected model.',
      )
    } finally {
      setChangingModelId(null)
    }
  }

  return (
    <fieldset className="workflow-lane-fieldset planning-agent-fieldset">
      <legend>
        Local LM Studio model <em>Required</em>
      </legend>
      {policyNote ? <p className="planning-agent-policy">{policyNote}</p> : null}
      <div className="workflow-lane-options">
        {LOCAL_PLANNING_AGENTS.map((agent) => (
          <label className="workflow-lane-card" key={agent.value}>
            <input
              type="radio"
              name={name}
              value={agent.value}
              checked={value === agent.value}
              required
              disabled={changingModelId !== null}
              onChange={() => {
                onChange(agent.value)
                onModelChange?.(null, agent.value)
              }}
            />
            <span>
              <b>{agent.label}</b>
              <small>{agent.description}</small>
            </span>
          </label>
        ))}
      </div>
      {liveModels.length ? (
        <div className="workflow-lane-options planning-model-options" aria-live="polite" style={{ marginTop: 10 }}>
          {liveModels.map((model) => {
            const selected =
              selectedModelId === model.model_id ||
              model.loaded_instance_ids.includes(selectedModelId ?? '')
            return (
              <label className="workflow-lane-card planning-model-card" key={`${model.key}:${model.model_id}`}>
                <input
                  type="radio"
                  name={`${name}-model`}
                  value={model.model_id}
                  checked={selected}
                  required
                  disabled={changingModelId !== null}
                  onChange={() => void selectModel(model)}
                />
                <span>
                  <b>{model.display_name}</b>
                  <small>
                    {changingModelId === model.model_id
                      ? 'Loading in LM Studio…'
                      : modelDetails(model)}
                  </small>
                </span>
              </label>
            )
          })}
        </div>
      ) : null}
      <div className="planning-model-status">
        <span>
          {loading
            ? 'Reading models from LM Studio…'
            : catalog?.reachable
              ? `${liveModels.length} LM Studio model${liveModels.length === 1 ? '' : 's'} available · refreshes automatically`
              : 'LM Studio is offline; showing configured fallbacks'}
        </span>
        <button
          type="button"
          onClick={() => void refresh(true)}
          disabled={loading || changingModelId !== null}
        >
          ↻ Refresh models
        </button>
      </div>
      {error ? <p className="studio-composer-error" role="status">{error}</p> : null}
    </fieldset>
  )
}
