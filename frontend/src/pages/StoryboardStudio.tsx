import type { PageId } from '../components/AppShell'
import { StudioProvider } from '../studio/StudioContext'
import { StudioRouter } from '../studio/StudioRouter'
import type { ProjectWorkflowLane } from '../workflowLanes'

export type StudioPage = PageId

type StoryboardStudioProps = {
  page: StudioPage
  projectId: string
  workflowLane: ProjectWorkflowLane | null
  backendStatus: string
  onNavigate: (page: PageId) => void
}

export function StoryboardStudio({
  page,
  projectId,
  workflowLane,
  backendStatus,
  onNavigate,
}: StoryboardStudioProps) {
  return (
    <StudioProvider
      projectId={projectId}
      workflowLane={workflowLane}
      backendStatus={backendStatus}
      onNavigate={onNavigate}
    >
      <StudioRouter page={page} />
    </StudioProvider>
  )
}
