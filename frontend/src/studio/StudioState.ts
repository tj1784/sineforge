import { createContext, useContext, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import type { PageId } from '../components/AppShell'
import type { ProjectWorkflowLane } from '../workflowLanes'
import type {
  Readiness,
  Shot,
  ShotNarrationPayload,
  ShotPromptPackagePayload,
  ShotUpdatePayload,
  StoryboardAggregate,
  VoiceProfileCreatePayload,
} from '../api/client'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error' | 'empty'

export type StudioContextValue = {
  backendStatus: string
  navigate: (page: PageId) => void
  workflowLane: ProjectWorkflowLane | null
  projectId: string
  setProjectId: (value: string) => void
  storyId: string
  setStoryId: (value: string) => void
  data: StoryboardAggregate | null
  readiness: Readiness | null
  message: string
  setMessage: (value: string) => void
  loadState: LoadState
  error: string | null
  selectedShot: Shot | null
  setSelectedShot: Dispatch<SetStateAction<Shot | null>>
  animaticOpen: boolean
  setAnimaticOpen: (open: boolean) => void
  busy: boolean
  reload: (id?: string) => Promise<void>
  createStory: (event: FormEvent<HTMLFormElement>) => Promise<void>
  loadExistingStory: (storyId: string) => Promise<void>
  addHierarchy: (kind: 'chapter' | 'scene' | 'shot') => Promise<void>
  addCharacter: (payload: {
    name: string
    role?: string
    physical_description?: string
  }) => Promise<void>
  addVoice: (payload: VoiceProfileCreatePayload) => Promise<boolean>
  saveShot: (shotId: string, payload: ShotUpdatePayload) => Promise<void>
  saveNarration: (shotId: string, payload: ShotNarrationPayload) => Promise<void>
  savePromptPackage: (shotId: string, payload: ShotPromptPackagePayload) => Promise<void>
  approvePlan: (approvedBy: string) => Promise<void>
  updateStoryFields: (payload: Record<string, unknown>) => Promise<void>
}

export const StudioContext = createContext<StudioContextValue | null>(null)

export function useStudio(): StudioContextValue {
  const ctx = useContext(StudioContext)
  if (!ctx) {
    throw new Error('useStudio must be used within StudioProvider')
  }
  return ctx
}
