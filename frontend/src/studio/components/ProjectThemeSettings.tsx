import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type Project } from '../../api/client'
import { ThemeSelector } from '../../components/ThemeSelector'
import {
  biblicalContextDraft,
  biblicalContextPayload,
  type BiblicalContextDraft,
  type CreativeThemeId,
} from '../../themes'

type ProjectThemeSettingsProps = {
  projectId: string
  disabled?: boolean
  onMessage: (message: string) => void
}

export function ProjectThemeSettings({ projectId, disabled = false, onMessage }: ProjectThemeSettingsProps) {
  const [project, setProject] = useState<Project | null>(null)
  const [themeId, setThemeId] = useState<CreativeThemeId>('default')
  const [context, setContext] = useState<BiblicalContextDraft>(() => biblicalContextDraft(null))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.getProject(projectId)
      setProject(result)
      setThemeId(result.theme_id)
      setContext(biblicalContextDraft(result.theme_context))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load the project theme.')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    const payload = themeId === 'biblical' ? biblicalContextPayload(context) : null
    if (themeId === 'biblical' && !payload) {
      setError('Complete every required Biblical context field before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateProjectTheme(projectId, {
        theme_id: themeId,
        theme_context: payload,
      })
      setProject(updated)
      setThemeId(updated.theme_id)
      setContext(biblicalContextDraft(updated.theme_context))
      onMessage(`${updated.theme_id === 'default' ? 'Default' : updated.theme_id === 'greek_mythology' ? 'Greek Mythology Theme' : 'Biblical Theme'} saved for future iterations.`)
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : 'Could not save the project theme.'
      setError(message)
      onMessage(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="panel stack-form project-theme-settings" onSubmit={(event) => void save(event)}>
      <div className="panel-title">
        <div>
          <h2>Creative theme</h2>
          <p>Controls content direction while preserving your own editable prompts and current workflow choices.</p>
        </div>
        <span className="truth-pill">{project?.theme_version ? `v${project.theme_version}` : loading ? 'Loading…' : 'Unavailable'}</span>
      </div>
      <ThemeSelector
        name="project-settings-theme"
        value={themeId}
        context={context}
        disabled={disabled || loading || saving}
        onChange={(nextTheme) => {
          setThemeId(nextTheme)
          setError(null)
        }}
        onContextChange={(key, value) => {
          setContext((current) => ({ ...current, [key]: value }))
          setError(null)
        }}
      />
      <p className="notice" role="note">
        Changing the theme affects future prompt compilations and generation iterations only. Existing prompts, accepted media, and run snapshots are never rewritten.
      </p>
      {error ? <p className="notice error" role="alert">{error}</p> : null}
      <div className="inline-actions">
        <button type="submit" className="primary-button touch-target" disabled={disabled || loading || saving}>
          {saving ? 'Saving theme…' : 'Save creative theme'}
        </button>
        <button type="button" className="ghost-button touch-target" onClick={() => void load()} disabled={loading || saving}>
          Refresh
        </button>
      </div>
    </form>
  )
}
