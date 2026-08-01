import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import type { PageId } from '../components/AppShell'
import type { ProjectWorkflowLane } from '../workflowLanes'
import {
  ApiError,
  BackendUnavailableError,
  api,
  normalizePhaseASnapshot,
  type Readiness,
  type Shot,
  type ShotNarrationPayload,
  type ShotPromptPackagePayload,
  type ShotUpdatePayload,
  type StoryboardAggregate,
  type VoiceProfileCreatePayload,
} from '../api/client'
import { demoAggregate, demoReadiness } from './demoPhaseA'
import { StudioContext, type LoadState, type StudioContextValue } from './StudioState'

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export function StudioProvider({
  projectId: selectedProjectId,
  workflowLane,
  backendStatus,
  onNavigate,
  children,
}: {
  projectId: string
  workflowLane: ProjectWorkflowLane | null
  backendStatus: string
  onNavigate: (page: PageId) => void
  children: ReactNode
}) {
  // Demo fallback only for the local demo UUID — never the legacy slug (App blocks slug studio routes).
  const isDemoProject = selectedProjectId === demoAggregate.story.project_id
  const [projectId, setProjectId] = useState(selectedProjectId || demoAggregate.story.project_id)
  const [storyId, setStoryId] = useState(isDemoProject ? demoAggregate.story.id : '')
  const [data, setData] = useState<StoryboardAggregate | null>(isDemoProject ? demoAggregate : null)
  const [readiness, setReadiness] = useState<Readiness | null>(isDemoProject ? demoReadiness : null)
  const [message, setMessage] = useState(
    isDemoProject
      ? 'A New Journey demo plan is loaded for this local Studio session. Server data remains canonical when available.'
      : 'Loading the selected project from the CineForge backend.',
  )
  const [loadState, setLoadState] = useState<LoadState>(isDemoProject ? 'ready' : 'loading')
  const [error, setError] = useState<string | null>(null)
  const [selectedShot, setSelectedShot] = useState<Shot | null>(null)
  const [animaticOpen, setAnimaticOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [projectLoadVersion, setProjectLoadVersion] = useState(0)
  const backendUnavailable = backendStatus === 'unavailable'

  const retryProjectLoad = useCallback(async () => {
    setProjectLoadVersion((current) => current + 1)
  }, [])

  const reload = useCallback(async (id = storyId) => {
    if (!id) {
      setLoadState('empty')
      setData(null)
      setReadiness(null)
      return
    }

    setBusy(true)
    setLoadState('loading')
    setError(null)
    try {
      const snapshot = await api.phaseA(id)
      const aggregate = normalizePhaseASnapshot(snapshot)
      setData(aggregate)
      setReadiness(snapshot.readiness)
      setStoryId(aggregate.story.id)
      setProjectId(aggregate.story.project_id)
      setLoadState('ready')
      setMessage('Live planning data loaded from the CineForge backend.')
      setSelectedShot((current) => {
        if (!current) return null
        for (const chapter of aggregate.chapters) {
          for (const scene of chapter.scenes) {
            const match = scene.shots.find((shot) => shot.id === current.id)
            if (match) return match
          }
        }
        return null
      })
    } catch (err) {
      const text = errorMessage(err, 'Unable to load storyboard data.')
      if (isDemoProject) {
        setData(demoAggregate)
        setReadiness(demoReadiness)
        setStoryId(demoAggregate.story.id)
        setProjectId(demoAggregate.story.project_id)
        setError(null)
        setLoadState('ready')
        setMessage(`${text} Showing the local A New Journey Phase A demo plan instead.`)
      } else {
        setData(null)
        setReadiness(null)
        setError(text)
        setLoadState('error')
        setMessage(text)
      }
    } finally {
      setBusy(false)
    }
  }, [isDemoProject, storyId])

  useEffect(() => {
    if (isDemoProject || backendUnavailable) return

    let active = true
    let retryTimer: number | undefined
    const loadSelectedProject = async () => {
      setBusy(true)
      setLoadState('loading')
      setError(null)
      setProjectId(selectedProjectId)
      try {
        const stories = await api.listStories(selectedProjectId)
        if (!active) return
        const story = stories[0]
        if (!story) {
          setStoryId('')
          setData(null)
          setReadiness(null)
          setLoadState('empty')
          setMessage('This project has no planning story yet. Create one below to begin Storyboard Studio work.')
          return
        }

        const snapshot = await api.phaseA(story.id)
        if (!active) return
        const aggregate = normalizePhaseASnapshot(snapshot)
        setData(aggregate)
        setReadiness(snapshot.readiness)
        setStoryId(aggregate.story.id)
        setProjectId(aggregate.story.project_id)
        setLoadState('ready')
        setMessage('')
      } catch (err) {
        if (!active) return
        const text = errorMessage(err, 'Unable to load the selected project in Storyboard Studio.')
        setData(null)
        setReadiness(null)
        setError(text)
        setLoadState('error')
        setMessage(text)
        if (err instanceof BackendUnavailableError) {
          retryTimer = window.setTimeout(
            () => setProjectLoadVersion((current) => current + 1),
            2_000,
          )
        }
      } finally {
        if (active) setBusy(false)
      }
    }

    void loadSelectedProject()
    return () => {
      active = false
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [backendUnavailable, isDemoProject, projectLoadVersion, selectedProjectId])

  const createStory = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const form = new FormData(event.currentTarget)
      setBusy(true)
      setError(null)
      try {
        const story = await api.createStory({
          project_id: String(form.get('project_id') ?? '').trim(),
          title: String(form.get('title') ?? '').trim(),
          base_story: String(form.get('base_story') ?? '').trim(),
          target_duration_sec: Number(form.get('target_duration_sec')),
        })
        setProjectId(story.project_id)
        setStoryId(story.id)
        await reload(story.id)
        setMessage(`Created planning story “${story.title}”. No rendering was started.`)
      } catch (err) {
        const text = errorMessage(err, 'Could not create story.')
        setError(text)
        setMessage(text)
        setLoadState('error')
      } finally {
        setBusy(false)
      }
    },
    [reload],
  )

  const loadExistingStory = useCallback(
    async (nextStoryId: string) => {
      const id = nextStoryId.trim()
      if (!id) {
        setMessage('Enter a story UUID to load.')
        return
      }
      setStoryId(id)
      await reload(id)
    },
    [reload],
  )

  const addHierarchy = useCallback(
    async (kind: 'chapter' | 'scene' | 'shot') => {
      if (!data) return
      const title = window.prompt(`New ${kind} title`)
      if (!title?.trim()) return

      setBusy(true)
      try {
        if (kind === 'chapter') {
          await api.createChapter(data.story.id, {
            title: title.trim(),
            order_index: data.chapters.length,
          })
        }

        if (kind === 'scene') {
          const chapter = data.chapters[data.chapters.length - 1] ?? data.chapters[0]
          if (!chapter) throw new Error('Create a chapter before adding a scene.')
          await api.createScene(chapter.id, {
            title: title.trim(),
            order_index: chapter.scenes.length,
          })
        }

        if (kind === 'shot') {
          const chapter = data.chapters[data.chapters.length - 1] ?? data.chapters[0]
          const scene = chapter?.scenes[chapter.scenes.length - 1] ?? chapter?.scenes[0]
          if (!scene) throw new Error('Create a scene before adding a shot.')
          const durationRaw = window.prompt('Shot duration in seconds (normal range 6–12)', '8')
          const duration = Number(durationRaw)
          if (!Number.isFinite(duration) || duration <= 0) {
            throw new Error('Shot duration must be a positive number.')
          }
          const reason =
            duration < 6 || duration > 12
              ? window.prompt('Override reason is required outside 6–12 seconds') ?? ''
              : undefined
          if ((duration < 6 || duration > 12) && !reason?.trim()) {
            throw new Error('Override reason is required for durations outside 6–12 seconds.')
          }
          await api.createShot(scene.id, {
            title: title.trim(),
            duration_sec: duration,
            duration_override_reason: reason?.trim() || undefined,
            order_index: scene.shots.length,
          })
        }

        await reload()
        setMessage(`Added ${kind}. Planning hierarchy updated on the server.`)
      } catch (err) {
        const text = errorMessage(err, 'Could not add planning item.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [data, reload],
  )

  const addCharacter = useCallback(
    async (payload: { name: string; role?: string; physical_description?: string }) => {
      if (!data) return
      setBusy(true)
      try {
        await api.createCharacter(data.story.id, payload)
        await reload()
        setMessage(`Character “${payload.name}” saved. No image generation was started.`)
      } catch (err) {
        const text = errorMessage(err, 'Could not add character.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [data, reload],
  )

  const addVoice = useCallback(
    async (payload: VoiceProfileCreatePayload): Promise<boolean> => {
      if (!data) return false
      setBusy(true)
      try {
        const created = await api.createVoiceProfile(data.story.id, payload)
        if (!created) {
          setMessage('Voice profile API is unavailable on this backend. No profile or preview was created.')
          return false
        }
        await reload()
        setMessage(
          `Voice profile “${payload.name}” saved as planning data. Cloning and audio generation were not performed.`,
        )
        return true
      } catch (err) {
        const text = errorMessage(err, 'Could not add voice profile.')
        setMessage(text)
        setError(text)
        return false
      } finally {
        setBusy(false)
      }
    },
    [data, reload],
  )

  const saveShot = useCallback(
    async (shotId: string, payload: ShotUpdatePayload) => {
      setBusy(true)
      try {
        await api.updateShot(shotId, payload)
        await reload()
        setMessage('Shot details saved to the backend.')
      } catch (err) {
        const text = errorMessage(err, 'Could not save shot.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [reload],
  )

  const saveNarration = useCallback(
    async (shotId: string, payload: ShotNarrationPayload) => {
      setBusy(true)
      try {
        await api.putShotNarration(shotId, payload)
        await reload()
        setMessage('Shot narration saved through the canonical narration resource.')
      } catch (err) {
        const text = errorMessage(err, 'Could not save shot narration.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [reload],
  )

  const savePromptPackage = useCallback(
    async (shotId: string, payload: ShotPromptPackagePayload) => {
      setBusy(true)
      try {
        await api.createShotPromptPackage(shotId, payload)
        await reload()
        setMessage('A new versioned prompt package was saved for this shot.')
      } catch (err) {
        const text = errorMessage(err, 'Could not save the shot prompt package.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [reload],
  )

  const approvePlan = useCallback(
    async (approvedBy: string) => {
      if (!data) return
      setBusy(true)
      try {
        await api.approveStoryboard(data.story.id, approvedBy, data.revision)
        await reload()
        setMessage(
          'Production plan approved. No timeline slot, queue job, ComfyUI submission, or FFmpeg job was created.',
        )
      } catch (err) {
        if (err instanceof ApiError) {
          setMessage(
            'Approval blocked by backend readiness gates. Review the readiness reasons returned by the server.',
          )
        } else {
          setMessage(errorMessage(err, 'Approval failed.'))
        }
        setError(errorMessage(err, 'Approval failed.'))
      } finally {
        setBusy(false)
      }
    },
    [data, reload],
  )

  const updateStoryFields = useCallback(
    async (payload: Record<string, unknown>) => {
      if (!data) return
      setBusy(true)
      try {
        await api.updateStory(data.story.id, payload, data.revision)
        await reload()
        setMessage('Story fields updated on the server.')
      } catch (err) {
        const text = errorMessage(err, 'Could not update story.')
        setMessage(text)
        setError(text)
      } finally {
        setBusy(false)
      }
    },
    [data, reload],
  )

  const value = useMemo<StudioContextValue>(
    () => ({
      backendStatus,
      navigate: onNavigate,
      workflowLane,
      projectId,
      setProjectId,
      storyId,
      setStoryId,
      data,
      readiness,
      message,
      setMessage,
      loadState,
      error,
      selectedShot,
      setSelectedShot,
      animaticOpen,
      setAnimaticOpen,
      busy,
      retryProjectLoad,
      reload,
      createStory,
      loadExistingStory,
      addHierarchy,
      addCharacter,
      addVoice,
      saveShot,
      saveNarration,
      savePromptPackage,
      approvePlan,
      updateStoryFields,
    }),
    [
      backendStatus,
      onNavigate,
      workflowLane,
      projectId,
      storyId,
      data,
      readiness,
      message,
      loadState,
      error,
      selectedShot,
      animaticOpen,
      busy,
      retryProjectLoad,
      reload,
      createStory,
      loadExistingStory,
      addHierarchy,
      addCharacter,
      addVoice,
      saveShot,
      saveNarration,
      savePromptPackage,
      approvePlan,
      updateStoryFields,
    ],
  )

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
}
