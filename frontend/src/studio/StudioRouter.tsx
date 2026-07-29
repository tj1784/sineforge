import type { PageId } from '../components/AppShell'
import { useStudio } from './StudioState'
import { StudioChrome } from './components/StudioChrome'
import { StoryBootstrap } from './components/StoryBootstrap'
import { OverviewPage } from './pages/OverviewPage'
import { StoryboardPage } from './pages/StoryboardPage'
import { StoryPage } from './pages/StoryPage'
import { CharactersPage } from './pages/CharactersPage'
import { VoicesPage } from './pages/VoicesPage'
import { ImagesPage } from './pages/ImagesPage'
import { RoutingPage } from './pages/RoutingPage'
import { WorkflowsPage } from './pages/WorkflowsPage'
import { ApiCallerPage } from './pages/ApiCallerPage'
import { DownloadsPage } from './pages/DownloadsPage'
import { ExportsPage } from './pages/ExportsPage'
import { SettingsPage } from './pages/SettingsPage'

const PAGE_META: Record<PageId, { title: string; description: string }> = {
  overview: {
    title: 'Overview',
    description: 'Seven connected production workspaces with live planning evidence and backend diagnostics.',
  },
  storyboard: {
    title: 'Storyboard',
    description: 'Ordered Chapter → Scene → Shot hierarchy with shot inspector.',
  },
  story: {
    title: 'Story & Chapters',
    description: 'Story intake, synopsis, and ordered chapter structure.',
  },
  characters: {
    title: 'Characters',
    description: 'Identity references, character profiles, continuity rules, and reference-view planning.',
  },
  voices: {
    title: 'Voices',
    description: 'Voice profiles, consent, recipes, mappings, and explicit provider-safe preview jobs.',
  },
  images: {
    title: 'Starting Images',
    description: 'Review managed reference assets and clean shot-level starting-image mappings.',
  },
  routing: {
    title: 'Model Routing',
    description: 'Factual model catalog evidence — Unknown remains unknown until evidence is recorded.',
  },
  workflows: {
    title: 'Workflows',
    description: 'Factual workflow-template catalog, admission evidence, and production routing.',
  },
  'api-caller': {
    title: 'API Caller',
    description: 'Mutable local API workflow library, right-panel input editor, validation, and explicit queue submission.',
  },
  downloads: {
    title: 'Downloads',
    description: 'Pinned model download candidates, verified local files, and source references.',
  },
  exports: {
    title: 'Exports',
    description: 'Planning exports plus the final assembly, manifest, and provenance destination.',
  },
  settings: {
    title: 'Project Settings',
    description: 'Duration, approval, continuity, consent, and aspect policies from the server.',
  },
}

export function StudioRouter({ page }: { page: PageId }) {
  const { data, loadState } = useStudio()

  if (!data || loadState === 'empty') {
    return <StoryBootstrap />
  }

  const meta = PAGE_META[page]
  const content = {
    overview: <OverviewPage />,
    storyboard: <StoryboardPage key={data.revision} />,
    story: <StoryPage key={data.revision} />,
    characters: <CharactersPage />,
    voices: <VoicesPage />,
    images: <ImagesPage />,
    routing: <RoutingPage />,
    workflows: <WorkflowsPage />,
    'api-caller': <ApiCallerPage />,
    downloads: <DownloadsPage />,
    exports: <ExportsPage />,
    settings: <SettingsPage />,
  }[page]
  const pageOwnsLayout = !(['overview', 'characters', 'settings'] as PageId[]).includes(page)

  return (
    <StudioChrome title={meta.title} description={meta.description}>
      {pageOwnsLayout ? content : <div className="page">{content}</div>}
    </StudioChrome>
  )
}
