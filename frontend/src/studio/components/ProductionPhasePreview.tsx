import { useMemo, useState } from 'react'

import type { PageId } from '../../components/AppShell'
import { api, type ProductionPhase } from '../../api/client'
import {
  type SnapshotCharacter,
  type SnapshotScene,
  type SnapshotShot,
  type SnapshotWorkspace,
} from '../snapshotWorkspace'
import { artDirectionBoardUrl, characterPortraitUrl, startingFrameUrl } from '../mediaUrls'
import { formatDuration, initials } from '../utils'

type PreviewProps = {
  phase: ProductionPhase
  workspace: SnapshotWorkspace | null
  historical: boolean
  incompleteReason?: string | null
  productionProfileKey?: 'ltx_base@1' | 'wan_base@1'
  stitchStage?: 'phase7_before_audio' | 'phase8_before_foley'
  onNavigate?: (page: PageId) => void
}

type SceneRow = {
  chapterTitle: string
  scene: SnapshotScene
  sceneNumber: number
  shots: SnapshotShot[]
}

type ShotRow = {
  chapterTitle: string
  sceneId: string
  sceneTitle: string
  sceneNumber: number
  shotNumber: number
  code: string
  shot: SnapshotShot
}

const NINE_PANEL_LABELS = [
  'Full body',
  'Front portrait',
  'Three-quarter',
  'Side profile',
  'Neutral',
  'Concerned',
  'Overwhelmed',
  'Focused',
  'Reflective',
] as const

const WORKFLOW_STATES = [
  ['Available', 'Registered and visible in the runtime catalog.'],
  ['Admitted', 'Validated for this production profile.'],
  ['Benchmark required', 'Evidence must be recorded before execution.'],
  ['Blocked', 'A policy or validation condition prevents execution.'],
  ['Unavailable', 'Not present in the current runtime.'],
] as const

function shotLetter(index: number): string {
  if (index < 26) return String.fromCharCode(65 + index)
  return String(index + 1)
}

function buildSceneRows(workspace: SnapshotWorkspace | null): SceneRow[] {
  if (!workspace) return []
  const chapterTitle = new Map(workspace.chapters.map((chapter) => [chapter.id, chapter.title]))
  const shotsByScene = new Map<string, SnapshotShot[]>()
  for (const shot of workspace.shots) {
    const sceneId = shot.scene_id || 'unknown'
    shotsByScene.set(sceneId, [...(shotsByScene.get(sceneId) ?? []), shot])
  }
  return workspace.scenes.map((scene, index) => ({
    chapterTitle: (scene.chapter_id && chapterTitle.get(scene.chapter_id)) || 'Chapter',
    scene,
    sceneNumber: index + 1,
    shots: shotsByScene.get(scene.id) ?? [],
  }))
}

function buildShotRows(scenes: SceneRow[]): ShotRow[] {
  return scenes.flatMap((row) =>
    row.shots.map((shot, index) => ({
      chapterTitle: row.chapterTitle,
      sceneId: row.scene.id,
      sceneTitle: row.scene.title,
      sceneNumber: row.sceneNumber,
      shotNumber: index + 1,
      code: `S${String(row.sceneNumber).padStart(2, '0')}${shotLetter(index)}`,
      shot,
    })),
  )
}

function lifecycleLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function editorLabel(label: string, historical: boolean) {
  return historical ? `Open current ${label}` : label
}

function productionProfilePresentation(profileKey: string | undefined) {
  if (profileKey === 'wan_base@1') {
    return {
      label: 'WAN Base v1',
      detail: 'Persisted selection · runtime qualification required',
    }
  }
  if (profileKey === 'ltx_base@1') {
    return {
      label: 'LTX Base v1',
      detail: 'Persisted compatibility profile',
    }
  }
  return {
    label: 'Not recorded',
    detail: 'No persisted production profile is available',
  }
}

function stitchStagePresentation(stitchStage: string | undefined) {
  if (stitchStage === 'phase8_before_foley') {
    return {
      label: 'Phase 8',
      detail: 'Picture stitch is deferred until the audio/delivery phase',
    }
  }
  if (stitchStage === 'phase7_before_audio') {
    return {
      label: 'Phase 7',
      detail: 'Lock and stitch picture before audio generation',
    }
  }
  return {
    label: 'Not recorded',
    detail: 'No persisted stitch stage is available',
  }
}

function continuityStatus(value: string | null | undefined): string {
  const normalized = (value || 'none').toLowerCase().replaceAll('_', ' ').trim()
  if (!normalized || normalized === 'none') return 'draft'
  if (normalized.includes('shot') || normalized.includes('ref')) return 'review'
  if (normalized.includes('approved') || normalized.includes('locked')) return 'approved'
  if (normalized.includes('block') || normalized.includes('missing')) return 'blocked'
  return 'local'
}

function PhasePreviewHeader({
  phase,
  description,
  source,
  actions,
  historical,
  onNavigate,
}: {
  phase: ProductionPhase
  description: string
  source: 'Live records' | 'Retained snapshot' | 'Derived preview' | 'Design template'
  actions?: Array<{ label: string; page: PageId }>
  historical: boolean
  onNavigate?: (page: PageId) => void
}) {
  return (
    <div className="phase-workspace-header">
      <div>
        <span className="eyebrow">PHASE {phase.phase_number} · {source.toUpperCase()}</span>
        <h3>{phase.name}</h3>
        <p>{description}</p>
      </div>
      <div className="phase-workspace-meta">
        <span className="phase-workspace-meta-pill">{historical ? 'Read-only history' : 'Design available'}</span>
        <small>Backend state · {lifecycleLabel(phase.lifecycle_state)}</small>
        {actions?.length && onNavigate ? (
          <div className="phase-header-actions" aria-label="Related workspaces">
            {actions.map((action) => (
              <button key={action.page} type="button" className="btn secondary" onClick={() => onNavigate(action.page)}>
                {editorLabel(action.label, historical)} <span aria-hidden="true">↗</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function WorkspaceMetric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <article className="phase-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  )
}

function PreviewDisclosure({ historical }: { historical: boolean }) {
  return (
    <div className="phase-preview-disclosure" role="note">
      <span aria-hidden="true">◇</span>
      <div>
        <b>{historical ? 'Immutable retained snapshot' : 'Interactive UI/UX preview'}</b>
        <p>
          {historical
            ? 'This workspace renders only the verified SQLite snapshot for the selected iteration. It never substitutes current draft records.'
            : 'This workspace reads current planning records for display. It does not start generation, submit jobs, call ComfyUI, synthesize voices, or run FFmpeg.'}
        </p>
      </div>
    </div>
  )
}

function EmptyDesignState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="phase-empty">
      <span aria-hidden="true">＋</span>
      <div><b>{title}</b><p>{detail}</p></div>
    </div>
  )
}

function IncompleteSnapshotState({ phaseNumber, reason }: { phaseNumber: number; reason: string }) {
  return (
    <div className="phase-history-error phase-legacy-incomplete" role="alert">
      <div>
        <b>Legacy snapshot is incomplete</b>
        <p>
          Phase {phaseNumber} cannot be reconstructed from this retained version alone.
          {' '}
          {reason}
          {' '}
          The current draft was not substituted.
        </p>
      </div>
    </div>
  )
}

function characterCompleteness(character: SnapshotCharacter): number {
  const fields = [
    character.name,
    character.role,
    character.age_range,
    character.physical_description,
    character.personality,
    character.speaking_style,
    character.wardrobe,
    character.consistency_prompt,
  ]
  return Math.round((fields.filter(Boolean).length / fields.length) * 100)
}

function statusToken(value: string | null | undefined): string {
  return (value || 'draft').toLowerCase().replaceAll('_', ' ').trim() || 'draft'
}

function PhaseTwoPreview({ phase, workspace, historical, onNavigate }: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const firstSceneId = scenes[0]?.scene.id ?? ''
  const [selectedSceneId, setSelectedSceneId] = useState(firstSceneId)
  const activeSceneId = scenes.some((item) => item.scene.id === selectedSceneId)
    ? selectedSceneId
    : firstSceneId
  const selectedScene = scenes.find((item) => item.scene.id === activeSceneId) ?? scenes[0] ?? null
  const selectedShots = selectedScene ? shots.filter((item) => item.sceneId === selectedScene.scene.id) : []
  const target = workspace?.targetDurationSec ?? 0
  const planned = shots.reduce((total, row) => total + Number(row.shot.duration_sec || 0), 0)
  const average = shots.length ? planned / shots.length : 0
  const continuityCount = shots.filter((row) => row.shot.continuity_source_shot_id).length
  const startFrameCount = shots.filter((row) => row.shot.starting_image_required || row.shot.starting_image_asset_id).length
  const mediaScope = {
    projectId: workspace?.projectId,
    storyTitle:
      typeof workspace?.narrative?.title === 'string' ? workspace.narrative.title : null,
  }
  const sceneBoardUrl = selectedScene
    ? artDirectionBoardUrl({
        sceneNumber: selectedScene.sceneNumber,
        ...mediaScope,
      })
    : null
  const sceneFrameUrls = selectedShots
    .map((row) => ({
      code: row.code,
      url: startingFrameUrl({
        code: row.code,
        title: row.shot.title,
        assetId: row.shot.starting_image_asset_id,
        ...mediaScope,
      }),
    }))
    .filter((item): item is { code: string; url: string } => Boolean(item.url))

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Live records'}
        description="Shape the approved narrative into a timed Chapter → Scene → Shot structure, then inspect duration, continuity, cast, and starting-frame intent in one place."
        actions={[{ label: 'Storyboard', page: 'storyboard' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics five">
        <WorkspaceMetric label="Chapters / acts" value={workspace?.chapters.length || '—'} />
        <WorkspaceMetric label="Scenes" value={scenes.length || '—'} />
        <WorkspaceMetric label="Shots" value={shots.length || '—'} detail={shots.length ? `${average.toFixed(1)}s average` : undefined} />
        <WorkspaceMetric label="Planned runtime" value={planned ? formatDuration(planned) : '—'} detail={target ? `${formatDuration(target)} target` : undefined} />
        <WorkspaceMetric label="Continuity links" value={shots.length ? continuityCount : '—'} detail={shots.length ? `${startFrameCount} start-frame requirements` : undefined} />
      </div>

      {scenes.length ? (
        <div className="phase-segmentation-layout">
          <aside className="phase-list" aria-label="Scene browser">
            <header><span>STRUCTURE</span><b>{scenes.length} scenes</b></header>
            {scenes.map((row) => (
              <button
                key={row.scene.id}
                type="button"
                className={row.scene.id === selectedScene?.scene.id ? 'active' : ''}
                onClick={() => setSelectedSceneId(row.scene.id)}
              >
                <span>{String(row.sceneNumber).padStart(2, '0')}</span>
                <div>
                  <b>{row.scene.title}</b>
                  <small>{row.shots.length} shots · {formatDuration(row.shots.reduce((t, s) => t + Number(s.duration_sec || 0), 0))}</small>
                </div>
              </button>
            ))}
          </aside>

          <section className="phase-inspector">
            <header>
              <div>
                <span>SCENE {String(selectedScene?.sceneNumber ?? 0).padStart(2, '0')}</span>
                <h4>{selectedScene?.scene.title}</h4>
                <p>{selectedScene?.scene.summary || 'No scene summary has been recorded.'}</p>
              </div>
              <b>{formatDuration(selectedShots.reduce((t, s) => t + Number(s.shot.duration_sec || 0), 0))}</b>
            </header>
            <div className="phase-mini-timeline" aria-label="Selected scene shot timing">
              {selectedShots.map((row) => (
                <span
                  key={row.shot.id}
                  style={{ flexGrow: Math.max(1, Number(row.shot.duration_sec || 1)) }}
                  title={`${row.code} · ${row.shot.duration_sec ?? 0}s`}
                >
                  {row.code}
                </span>
              ))}
            </div>
            {sceneBoardUrl ? (
              <figure className="phase-scene-board">
                <img
                  src={sceneBoardUrl}
                  alt={`${selectedScene?.scene.title ?? 'Scene'} storyboard board`}
                  loading="lazy"
                  decoding="async"
                />
                <figcaption>
                  SCENE {String(selectedScene?.sceneNumber ?? 0).padStart(2, '0')} · selected scene board
                </figcaption>
              </figure>
            ) : sceneFrameUrls.length ? (
              <div className="phase-frame-grid" aria-label="Selected scene starting frames">
                {sceneFrameUrls.slice(0, 6).map((frame, index) => (
                  <article key={frame.code}>
                    <div className={`frame-art frame-${index % 8} has-image`}>
                      <img src={frame.url} alt={`${frame.code} starting frame`} loading="lazy" decoding="async" />
                      <span>{frame.code}</span>
                    </div>
                    <b>{frame.code}</b>
                    <small>Starting frame</small>
                  </article>
                ))}
              </div>
            ) : null}
            <div className="phase-table-wrap">
              <table>
                <thead><tr><th>Shot</th><th>Purpose</th><th>Cast / location</th><th>Duration</th><th>Continuity</th></tr></thead>
                <tbody>
                  {selectedShots.map((row) => {
                    const purpose = row.shot.story_purpose || row.shot.visual_description || 'Not recorded'
                    const continuity = row.shot.continuity_source_type
                    const linked = Boolean(continuity && continuity !== 'none')
                    return (
                      <tr key={row.shot.id}>
                        <td><b>{row.code}</b><small>{row.shot.title}</small></td>
                        <td title={purpose}>{purpose}</td>
                        <td>
                          {row.shot.location || 'Location not mapped'}
                          <small>{row.shot.characters?.length ?? 0} cast links</small>
                        </td>
                        <td>{Number(row.shot.duration_sec || 0).toFixed(1)}s</td>
                        <td>
                          <span
                            className="status-pill"
                            data-status={linked ? 'ready' : continuityStatus(continuity)}
                            title={(continuity || 'none').replaceAll('_', ' ')}
                          >
                            {linked ? 'Linked' : 'None'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : (
        <EmptyDesignState
          title="The segmentation workspace is ready"
          detail={historical
            ? 'This retained snapshot has no chapters, scenes, or shots.'
            : 'No persisted chapters, scenes, or shots are available yet.'}
        />
      )}

      <div className="phase-footer">
        <div>
          <span>PLANNING DIAGNOSTICS</span>
          <b>Timing and coverage evidence</b>
          <p>
            {historical
              ? 'Calculated only from the retained snapshot.'
              : 'Calculated from current planning records—not a Phase 2 QA result.'}
            {shots.length
              ? ` · ${shots.filter((row) => Number(row.shot.duration_sec) >= 6 && Number(row.shot.duration_sec) <= 10).length}/${shots.length} shots in 6–10s · ${target && planned ? `${Math.abs(target - planned).toFixed(1)}s target delta` : 'no target delta'}`
              : ''}
          </p>
        </div>
        {onNavigate ? (
          <button type="button" className="btn primary" onClick={() => onNavigate('storyboard')}>
            {editorLabel('Edit in Storyboard', historical)}
          </button>
        ) : null}
      </div>
    </div>
  )
}

function PhaseThreePreview({ phase, workspace, historical, onNavigate }: PreviewProps) {
  const characters = workspace?.characters ?? []
  const firstCharacterId = characters[0]?.id ?? ''
  const [selectedId, setSelectedId] = useState(firstCharacterId)
  const activeCharacterId = characters.some((item) => item.id === selectedId)
    ? selectedId
    : firstCharacterId
  const selected = characters.find((item) => item.id === activeCharacterId) ?? characters[0] ?? null
  const references = selected?.reference_links ?? []
  const linkedShots = (workspace?.shots ?? []).filter((shot) =>
    shot.characters?.some((link) => link.character_id === selected?.id),
  )
  const voices = workspace?.voices ?? []
  const assignedVoices = characters.filter((item) => item.assigned_voice_profile_id).length
  const principalCast = characters.filter(
    (item) => (item.role || '').toLowerCase().includes('lead') || (item.reference_links?.length ?? 0) > 0,
  ).length
  const referenceLinks = characters.reduce((total, item) => total + (item.reference_links?.length ?? 0), 0)
  const mediaScope = {
    projectId: workspace?.projectId,
    storyTitle:
      typeof workspace?.narrative?.title === 'string' ? workspace.narrative.title : null,
  }
  const selectedPortraitUrl = selected
    ? characterPortraitUrl({
        name: selected.name,
        assetId: references[0]?.asset_id,
        ...mediaScope,
      })
    : null

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Live records'}
        description="Build distinct, continuity-safe character identities and review the required nine-view reference plan before any media is produced."
        actions={[{ label: 'Characters', page: 'characters' }, { label: 'Voices', page: 'voices' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics four">
        <WorkspaceMetric label="Characters" value={characters.length || '—'} />
        <WorkspaceMetric label="Principal cast" value={principalCast || '—'} />
        <WorkspaceMetric label="Reference links" value={referenceLinks || '—'} />
        <WorkspaceMetric
          label="Voice assignments"
          value={assignedVoices || '—'}
          detail={characters.length ? `${voices.length} voice profiles` : undefined}
        />
      </div>

      {selected ? (
        <div className="phase-character-layout">
          <aside className="phase-list character-list" aria-label="Character profiles">
            <header>
              <span>CAST</span>
              <b>{characters.length} profiles</b>
            </header>
            {characters.map((character) => (
              <button
                key={character.id}
                type="button"
                className={character.id === selected.id ? 'active' : ''}
                onClick={() => setSelectedId(character.id)}
              >
                <span>{initials(character.name)}</span>
                <div>
                  <b>{character.name}</b>
                  <small>{character.role || 'Role not recorded'}</small>
                </div>
                <i>{characterCompleteness(character)}%</i>
              </button>
            ))}
          </aside>

          <section className="phase-character-profile">
            <header>
              <span className={selectedPortraitUrl ? 'has-reference' : undefined}>
                {selectedPortraitUrl ? (
                  <img
                    src={selectedPortraitUrl}
                    alt={`${selected.name} reference`}
                    loading="lazy"
                    decoding="async"
                  />
                ) : initials(selected.name)}
              </span>
              <div>
                <small>CHARACTER PROFILE</small>
                <h4>{selected.name}</h4>
                <p>
                  {selected.role || 'Narrative role not recorded'}
                  {' · '}
                  {selected.age_range || 'Age range not recorded'}
                </p>
              </div>
              <span className="status-pill" data-status={statusToken(selected.approval_state)}>
                {selected.approval_state || 'draft'}
              </span>
            </header>
            <div className="phase-fact-grid">
              <article>
                <span>Physical identity</span>
                <p>{selected.physical_description || (historical ? 'Not recorded in this snapshot.' : 'Not recorded')}</p>
              </article>
              <article>
                <span>Personality & movement</span>
                <p>{selected.personality || (historical ? 'Not recorded in this snapshot.' : 'Not recorded')}</p>
              </article>
              <article>
                <span>Voice assignment</span>
                <p>
                  {selected.assigned_voice_profile_id
                    ? `Linked voice ${selected.assigned_voice_profile_id.slice(0, 8)}…`
                    : (historical ? 'No voice assignment in this snapshot.' : 'No voice assignment.')}
                </p>
              </article>
              <article>
                <span>Reference coverage</span>
                <p>{references.length} linked reference asset(s).</p>
              </article>
            </div>
            <div className="phase-continuity">
              <span>SHOT LINKS</span>
              <p>
                {linkedShots.length} linked shots in this {historical ? 'retained snapshot' : 'current draft'}.
              </p>
            </div>
          </section>

          <section className="phase-nine-panel">
            <header>
              <div>
                <span>NINE-PANEL SPECIFICATION</span>
                <h4>Reference-view plan</h4>
                <p>Each slot remains a planned requirement unless a real managed reference is linked.</p>
              </div>
              <b>{Math.min(9, references.length)}/9 linked</b>
            </header>
            <div>
              {NINE_PANEL_LABELS.map((label, index) => {
                const reference = references[index]
                // Slot 0 may use Transfiguration canon portrait when scoped; later slots need real links.
                const portraitUrl =
                  index === 0
                    ? characterPortraitUrl({
                        name: selected.name,
                        assetId: reference?.asset_id,
                        ...mediaScope,
                      })
                    : reference?.asset_id
                      ? characterPortraitUrl({
                          name: selected.name,
                          assetId: reference.asset_id,
                          ...mediaScope,
                        })
                      : null
                return (
                  <article key={label}>
                    <span className={portraitUrl ? 'has-reference' : undefined}>
                      {portraitUrl ? (
                        <img
                          src={portraitUrl}
                          alt={`${selected.name} ${label}`}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (index + 1)}
                    </span>
                    <b>{label}</b>
                    <small>
                      {reference
                        ? (reference.approved ? 'Approved reference' : 'Draft reference')
                        : portraitUrl
                          ? 'Canon portrait'
                          : 'Planned view'}
                    </small>
                  </article>
                )
              })}
            </div>
          </section>
        </div>
      ) : (
        <EmptyDesignState
          title="The character workspace is ready"
          detail={historical ? 'This retained snapshot has no character records.' : 'No character records are available for this story yet.'}
        />
      )}

      <div className="phase-footer">
        <div>
          <span>PROFILE COVERAGE</span>
          <b>Identity planning, not generated media</b>
          <p>
            Completeness is calculated only from
            {historical ? ' snapshot fields' : ' stored profile fields'}
            {' '}
            and reference links.
          </p>
        </div>
        {onNavigate ? (
          <div className="phase-header-actions">
            <button type="button" className="btn secondary" onClick={() => onNavigate('voices')}>
              {editorLabel('Review voices', historical)}
            </button>
            <button type="button" className="btn primary" onClick={() => onNavigate('characters')}>
              {editorLabel('Edit character profiles', historical)}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function PhaseFourPreview({ phase, workspace, historical }: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const locations = useMemo(() => {
    if (workspace?.locations.length) {
      return workspace.locations.map((name) => ({
        name,
        shots: shots.filter((row) => row.shot.location === name),
      }))
    }
    const values = new Map<string, ShotRow[]>()
    for (const row of shots) {
      const location = row.shot.location?.trim()
      if (!location) continue
      values.set(location, [...(values.get(location) ?? []), row])
    }
    return [...values.entries()].map(([name, locationShots]) => ({ name, shots: locationShots }))
  }, [shots, workspace])
  const firstLocation = locations[0]?.name ?? ''
  const [selectedLocation, setSelectedLocation] = useState(firstLocation)
  const activeLocation = locations.some((item) => item.name === selectedLocation)
    ? selectedLocation
    : firstLocation
  const selected = locations.find((item) => item.name === activeLocation) ?? locations[0] ?? null

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Derived preview'}
        description="Define reusable locations and story-critical assets, then trace geography, state, ownership, and continuity across every planned shot."
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics four">
        <WorkspaceMetric label="Derived locations" value={locations.length || '—'} detail={historical ? 'From retained snapshot' : 'From current shot records'} />
        <WorkspaceMetric label="Location coverage" value={shots.length ? `${shots.filter((row) => row.shot.location).length}/${shots.length}` : '—'} />
        <WorkspaceMetric label="Key-asset profiles" value={workspace?.keyAssets.length || '—'} detail="Schema design pending" />
        <WorkspaceMetric label="Continuity states" value="—" detail="Workspace template" />
      </div>

      <div className="phase-location-layout">
        <section aria-label="Location catalog">
          <header className="phase-subheading">
            <div>
              <span>LOCATION CATALOG</span>
              <h4>Environment coverage</h4>
              <p>
                {historical
                  ? 'Location names are taken only from the retained snapshot.'
                  : 'Location names are derived from persisted shots.'}
              </p>
            </div>
            <b>{locations.length || 0} sites</b>
          </header>
          {locations.length ? (
            <div className="phase-location-list">
              {locations.map((location, index) => (
                <button
                  key={location.name}
                  type="button"
                  className={location.name === selected?.name ? 'active' : ''}
                  onClick={() => setSelectedLocation(location.name)}
                >
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <b>{location.name}</b>
                    <small>
                      {location.shots.length} shots · first appears in{' '}
                      {location.shots[0]?.sceneTitle || 'snapshot'}
                    </small>
                  </div>
                  <i aria-hidden="true">›</i>
                </button>
              ))}
            </div>
          ) : (
            <EmptyDesignState
              title="No location values are recorded"
              detail={
                historical
                  ? 'This retained snapshot has no location catalog entries.'
                  : 'The location profile design remains available without inventing production data.'
              }
            />
          )}
        </section>

        <section className="phase-location-profile">
          <header>
            <div>
              <span>LOCATION PROFILE</span>
              <h4>{selected?.name || 'Select a location'}</h4>
              <p>
                {selected
                  ? `${selected.shots.length} shot uses are connected to this profile.`
                  : 'No location is selected.'}
              </p>
            </div>
            <span className="status-pill" data-status={historical ? 'review' : 'draft'}>
              {historical ? 'Snapshot' : 'Derived'}
            </span>
          </header>
          <div className="phase-fact-grid">
            {[
              ['Story purpose', selected?.shots[0]?.shot.story_purpose || 'Not recorded'],
              ['Geography & scale', 'Profile field ready for backend support'],
              ['Screen direction', 'Entrances, exits, landmarks, and camera access'],
              ['Light & weather', 'Time-of-day variants, palette, and material behavior'],
              ['Environmental sound', 'Ambience and recurring acoustic cues'],
              ['Forbidden drift', 'Geometry and landmark changes that must never occur'],
            ].map(([label, value]) => (
              <article key={label}>
                <span>{label}</span>
                <p>{value}</p>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="phase-key-assets">
        <header className="phase-subheading">
          <div>
            <span>KEY-ASSET REGISTRY</span>
            <h4>Story-critical object continuity</h4>
            <p>
              {workspace?.keyAssets.length
                ? `${workspace.keyAssets.length} key-asset record(s) are present in this ${historical ? 'snapshot' : 'draft'}.`
                : 'No canonical key-asset rows are present, so this structure stays truthful and unpopulated.'}
            </p>
          </div>
          <b>Design template</b>
        </header>
        <div>
          {[
            ['Identity', 'Canonical name, function, size, shape, material, color'],
            ['Condition', 'Age, wear, damage state, and allowed transformations'],
            ['Ownership', 'Owner, location, movement, and interaction rules'],
            ['Shot mapping', 'State per shot and continuity-change timeline'],
            ['References', 'Front, side, three-quarter, detail, and scale views'],
          ].map(([title, detail], index) => (
            <article key={title}>
              <span>{index + 1}</span>
              <div>
                <b>{title}</b>
                <p>{detail}</p>
              </div>
              <small>Field group</small>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

function PhaseFivePreview({ phase, workspace, historical, onNavigate }: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const firstShotId = shots[0]?.shot.id ?? ''
  const [selectedShotId, setSelectedShotId] = useState(firstShotId)
  const [promptTab, setPromptTab] = useState<'image' | 'video' | 'negative'>('image')
  const activeShotId = shots.some((item) => item.shot.id === selectedShotId)
    ? selectedShotId
    : firstShotId
  const selected = shots.find((item) => item.shot.id === activeShotId) ?? shots[0] ?? null
  const promptCoverage = shots.filter((row) => row.shot.image_prompt && row.shot.video_prompt && row.shot.negative_prompt).length
  const promptText = selected
    ? {
        image: selected.shot.image_prompt,
        video: selected.shot.video_prompt,
        negative: selected.shot.negative_prompt,
      }[promptTab]
    : null

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Live records'}
        description="Review every generation instruction, reference dependency, workflow recommendation, and technical setting before media production begins."
        actions={[{ label: 'Routing', page: 'routing' }, { label: 'Workflows', page: 'workflows' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics five">
        <WorkspaceMetric label="Shot packages" value={shots.length ? `${promptCoverage}/${shots.length}` : '—'} detail="Image + video + negative" />
        <WorkspaceMetric label="Prompt package rows" value={workspace?.promptPackages.length || '—'} />
        <WorkspaceMetric label="Character prompts" value={workspace?.characters.length || '—'} />
        <WorkspaceMetric label="Voice packages" value={workspace?.voices.length || '—'} />
        <WorkspaceMetric label="Target runtime" value={workspace ? formatDuration(workspace.targetDurationSec) : '—'} />
      </div>

      {selected ? (
        <div className="phase-prompt-layout">
          <aside className="phase-list prompt-list" aria-label="Shot prompt packages">
            <header>
              <span>SHOT PACKAGES</span>
              <b>
                {promptCoverage}/{shots.length} complete
              </b>
            </header>
            {shots.map((row) => (
              <button
                key={row.shot.id}
                type="button"
                className={row.shot.id === selected.shot.id ? 'active' : ''}
                onClick={() => setSelectedShotId(row.shot.id)}
              >
                <span>{row.code}</span>
                <div>
                  <b>{row.shot.title}</b>
                  <small>{row.sceneTitle}</small>
                </div>
                <i className={row.shot.image_prompt ? 'has-record' : ''} aria-hidden="true">
                  {row.shot.image_prompt ? '●' : '○'}
                </i>
              </button>
            ))}
          </aside>
          <section className="phase-prompt-inspector">
            <header>
              <div>
                <span>
                  {selected.code} · PROMPT PACKAGE
                </span>
                <h4>{selected.shot.title}</h4>
                <p>
                  {selected.shot.visual_description ||
                    selected.shot.story_purpose ||
                    'No visual description has been recorded.'}
                </p>
              </div>
            </header>
            <div className="phase-inline-tabs" role="tablist" aria-label="Prompt type">
              {(['image', 'video', 'negative'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={promptTab === tab}
                  className={promptTab === tab ? 'active' : ''}
                  onClick={() => setPromptTab(tab)}
                >
                  {tab} prompt
                </button>
              ))}
            </div>
            <div className="phase-prompt-copy">
              <span>{promptTab.toUpperCase()} PROMPT</span>
              <p>
                {promptText ||
                  `No ${promptTab} prompt has been stored for this shot in the ${historical ? 'snapshot' : 'current draft'}.`}
              </p>
            </div>
            <div className="phase-fact-grid">
              <article>
                <span>Camera</span>
                <p>{selected.shot.camera_direction || 'No camera direction recorded.'}</p>
              </article>
              <article>
                <span>Motion</span>
                <p>{selected.shot.motion_direction || 'No motion direction recorded.'}</p>
              </article>
              <article>
                <span>Cast links</span>
                <p>{selected.shot.characters?.length ?? 0} character link(s)</p>
              </article>
              <article>
                <span>Style context</span>
                <p>{String(workspace?.narrative?.visual_style || 'No style lock recorded.')}</p>
              </article>
            </div>
          </section>
        </div>
      ) : (
        <EmptyDesignState
          title="The prompt-package workspace is ready"
          detail={historical ? 'This retained snapshot has no shot prompt packages.' : 'No persisted shots exist yet.'}
        />
      )}

      <section className="phase-workflow-evidence">
        <header className="phase-subheading">
          <div>
            <span>WORKFLOW EVIDENCE</span>
            <h4>Recommendation states stay explicit</h4>
            <p>Catalog visibility never implies that a workflow can execute.</p>
          </div>
        </header>
        <div>
          {WORKFLOW_STATES.map(([label, detail]) => {
            const state = label.toLowerCase().replaceAll(' ', '-')
            return (
              <article key={label}>
                <i data-state={state} aria-hidden="true" />
                <div>
                  <b>{label}</b>
                  <p>{detail}</p>
                </div>
              </article>
            )
          })}
        </div>
        {onNavigate ? (
          <div className="phase-footer-actions">
            <button type="button" className="btn secondary" onClick={() => onNavigate('routing')}>
              {editorLabel('Review model routing', historical)}
            </button>
            <button type="button" className="btn primary" onClick={() => onNavigate('workflows')}>
              {editorLabel('Review workflow catalog', historical)}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  )
}

function PhaseSixPreview({ phase, workspace, historical, onNavigate }: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const mediaScope = {
    projectId: workspace?.projectId,
    storyTitle:
      typeof workspace?.narrative?.title === 'string' ? workspace.narrative.title : null,
  }
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const [mediaTab, setMediaTab] = useState<'images' | 'voices' | 'mapping'>('images')
  const requiredFrames = shots.filter((row) => row.shot.starting_image_required || row.shot.starting_image_asset_id)
  const mappedFrames = requiredFrames.filter((row) => row.shot.starting_image_asset_id)
  const characterReferences = (workspace?.characters ?? []).reduce((total, character) => total + (character.reference_links?.length ?? 0), 0)
  const voices = workspace?.voices ?? []
  const assignedVoices = (workspace?.characters ?? []).filter((character) => character.assigned_voice_profile_id).length

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Live records'}
        description="Review character references, location art direction, clean starting frames, voice profiles, and their shot-level mappings in one production dashboard."
        actions={[{ label: 'Starting Images', page: 'images' }, { label: 'Voices', page: 'voices' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics five">
        <WorkspaceMetric label="Character refs" value={characterReferences || '—'} detail={`${workspace?.characters.length ?? 0} profiles`} />
        <WorkspaceMetric label="Starting frames" value={requiredFrames.length ? `${mappedFrames.length}/${requiredFrames.length}` : '—'} />
        <WorkspaceMetric label="Voice profiles" value={voices.length || '—'} detail={`${assignedVoices} character assignments`} />
        <WorkspaceMetric label="Media refs" value={workspace?.planningMedia.length || '—'} />
        <WorkspaceMetric label="Video generated" value="No" detail="Phase boundary preserved" />
      </div>

      <div className="phase-inline-tabs phase-media-tabs" role="tablist" aria-label="Phase 6 media view">
        {(['images', 'voices', 'mapping'] as const).map((tab) => (
          <button key={tab} type="button" role="tab" aria-selected={mediaTab === tab} className={mediaTab === tab ? 'active' : ''} onClick={() => setMediaTab(tab)}>
            {tab === 'images' ? 'Image assets' : tab === 'voices' ? 'Voice assets' : 'Shot mapping'}
          </button>
        ))}
      </div>

      {mediaTab === 'images' ? (
        <div className="phase-media-layout">
          <section>
            <div className="phase-subheading">
              <div>
                <span>STARTING-FRAME GALLERY</span>
                <h3>Clean frame coverage</h3>
                <p>Only real managed asset IDs from the {historical ? 'snapshot' : 'current draft'} render.</p>
              </div>
              <b>{mappedFrames.length}/{requiredFrames.length || 0} mapped</b>
            </div>
            {requiredFrames.length ? (
              <div className="phase-frame-grid">
                {requiredFrames.slice(0, 12).map((row, index) => {
                  const frameUrl = startingFrameUrl({
                    title: row.shot.title,
                    code: row.code,
                    assetId: row.shot.starting_image_asset_id,
                    ...mediaScope,
                  })
                  return (
                    <article key={row.shot.id}>
                      {/* Gold Sites: .frame-art + .frame-N + optional .has-image */}
                      <div
                        className={`frame-art frame-${index % 8}${frameUrl ? ' has-image' : ''}`}
                      >
                        {frameUrl ? (
                          <img
                            src={frameUrl}
                            alt={`${row.code} starting frame`}
                            loading="lazy"
                            decoding="async"
                            onError={(event) => {
                              const img = event.currentTarget
                              img.style.display = 'none'
                              img.parentElement?.classList.remove('has-image')
                            }}
                          />
                        ) : null}
                        <span>{row.code}</span>
                      </div>
                      <span
                        className="status-pill"
                        data-status={frameUrl ? 'ready' : 'draft'}
                      >
                        {frameUrl ? 'Mapped' : 'Planned'}
                      </span>
                      <b>{row.code} · {row.shot.title}</b>
                      <small>{frameUrl ? 'Frame attached' : 'Starting frame planned'}</small>
                    </article>
                  )
                })}
              </div>
            ) : (
              <EmptyDesignState
                title="No starting-frame requirements are recorded"
                detail={historical ? 'This retained snapshot has no starting-frame mappings.' : 'The gallery will display managed assets as soon as shots declare a requirement.'}
              />
            )}
          </section>
          <aside className="phase-media-summary">
            <span>CHARACTER MEDIA</span>
            <h3>Nine-view coverage</h3>
            <ul>
              {(workspace?.characters ?? []).map((character) => (
                <li key={character.id}>
                  <span>{initials(character.name)}</span>
                  <div>
                    <b>{character.name}</b>
                    <small>{character.reference_links?.length ?? 0}/9 linked views</small>
                  </div>
                  <i>{character.approval_state || 'draft'}</i>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      ) : null}

      {mediaTab === 'voices' ? (
        <section className="phase-voice-board">
          <div className="phase-subheading">
            <div>
              <span>VOICE & AUDIO BOARD</span>
              <h3>Profiles, consent, and timing</h3>
              <p>These are planning records from the {historical ? 'retained snapshot' : 'current draft'}; this view never requests synthesis.</p>
            </div>
            <b>{voices.length} profiles</b>
          </div>
          {voices.length ? (
            <div className="phase-voice-grid">
              {voices.map((voice) => (
                <article key={voice.id}>
                  <div className="phase-audio-wave" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
                  <span className="phase-evidence-pill">{voice.approval_state || 'draft'}</span>
                  <h4>{voice.name}</h4>
                  <p>{voice.tone || voice.design_description || 'Voice direction has not been recorded.'}</p>
                  <dl>
                    <div><dt>Mode</dt><dd>{(voice.setup_mode || 'unknown').replaceAll('_', ' ')}</dd></div>
                    <div><dt>Provider</dt><dd>{voice.provider || 'Not selected'}</dd></div>
                    <div><dt>Consent</dt><dd>{voice.consent_confirmed ? 'Confirmed' : 'Pending / unknown'}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          ) : (
            <EmptyDesignState
              title="No voice profiles are stored"
              detail={historical ? 'This retained snapshot has no voice profiles.' : 'The Voice workspace remains connected to the existing provider-safe setup flow.'}
            />
          )}
        </section>
      ) : null}

      {mediaTab === 'mapping' ? (
        <section className="phase-mapping-board">
          <div className="phase-subheading">
            <div>
              <span>CANONICAL MAPPING</span>
              <h3>Shot input manifest</h3>
              <p>Every row connects {historical ? 'snapshot' : 'current'} planning records without fabricating media provenance.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Shot</th><th>Starting frame</th><th>Cast</th><th>Voice</th><th>Prompt</th></tr></thead>
              <tbody>
                {shots.map((row) => (
                  <tr key={row.shot.id}>
                    <td><b>{row.code}</b><small>{row.shot.title}</small></td>
                    <td>{row.shot.starting_image_asset_id ? 'Mapped asset' : row.shot.starting_image_required ? 'Planned' : 'Not required'}</td>
                    <td>{row.shot.characters?.length ?? 0} links</td>
                    <td>{row.shot.voice_profile_id ? 'Mapped' : row.shot.narration_text ? 'Profile needed' : 'No speech'}</td>
                    <td>{row.shot.image_prompt && row.shot.video_prompt ? 'Package present' : 'Incomplete'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {onNavigate ? (
        <div className="phase-footer">
          <div>
            <span>CONNECTED WORKSPACES</span>
            <b>{historical ? 'Editor links open the current draft' : 'Review and edit the live records'}</b>
            <p>{historical ? 'Navigating away leaves this immutable snapshot unchanged.' : 'These actions navigate to existing backend-connected editors.'}</p>
          </div>
          <div className="phase-footer-actions">
            <button type="button" className="secondary-button" onClick={() => onNavigate('characters')}>{editorLabel('Character references', historical)}</button>
            <button type="button" className="secondary-button" onClick={() => onNavigate('voices')}>{editorLabel('Voice profiles', historical)}</button>
            <button type="button" className="primary-button" onClick={() => onNavigate('images')}>{editorLabel('Starting images', historical)}</button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function PhaseSevenPreview({
  phase,
  workspace,
  historical,
  productionProfileKey,
  stitchStage,
  onNavigate,
}: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const planned = shots.reduce((total, row) => total + Number(row.shot.duration_sec || 0), 0)
  const [pictureTab, setPictureTab] = useState<'timeline' | 'review' | 'manifest'>('timeline')
  const picture = workspace?.picture ?? workspace?.assembly
  const profile = productionProfilePresentation(
    historical ? String(picture?.production_profile_key || '') : productionProfileKey,
  )
  const stitch = stitchStagePresentation(
    historical ? String(picture?.stitch_stage || '') : stitchStage,
  )
  const pictureLocked = Boolean(picture?.picture_locked)
  const qaState = String(picture?.qa_state || 'not_evaluated')
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [videoUploadState, setVideoUploadState] = useState<
    'idle' | 'uploading' | 'complete' | 'error'
  >('idle')
  const [videoUploadMessage, setVideoUploadMessage] = useState('')

  async function uploadVideoSource() {
    if (!workspace?.projectId || !videoFile || historical) return
    setVideoUploadState('uploading')
    setVideoUploadMessage('')
    try {
      const result = await api.uploadVideoSourceAsset(
        workspace.projectId,
        videoFile,
      )
      if (!result) throw new Error('Video ingest endpoint is unavailable.')
      setVideoUploadState('complete')
      setVideoUploadMessage(
        result.created
          ? `Managed source ${result.asset.original_filename || result.asset.id} was added.`
          : `That video already exists as managed source ${result.asset.id}.`,
      )
      setVideoFile(null)
    } catch (error) {
      setVideoUploadState('error')
      setVideoUploadMessage(
        error instanceof Error ? error.message : 'Video ingest failed.',
      )
    }
  }

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Design template'}
        description="Generate and select video segments, verify continuity, establish the canonical edit, and lock picture before downstream Foley and final delivery."
        actions={[{ label: 'Workflows', page: 'workflows' }, { label: 'Exports', page: 'exports' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics five">
        <WorkspaceMetric label="Production profile" value={profile.label} detail={profile.detail} />
        <WorkspaceMetric label="Stitch stage" value={stitch.label} detail={stitch.detail} />
        <WorkspaceMetric label="Planned shots" value={shots.length || '—'} />
        <WorkspaceMetric label="Picture runtime" value={planned ? formatDuration(planned) : '—'} />
        <WorkspaceMetric
          label="Picture lock"
          value={pictureLocked ? 'Locked' : 'Not locked'}
          detail="Phase 8 must consume an immutable picture-lock reference"
        />
      </div>

      <div className="phase-inline-tabs phase-major-tabs" role="tablist" aria-label="Phase 7 picture-lock view">
        {(['timeline', 'review', 'manifest'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={pictureTab === tab}
            className={pictureTab === tab ? 'active' : ''}
            onClick={() => setPictureTab(tab)}
          >
            {tab === 'timeline' ? 'Picture timeline' : tab === 'review' ? 'Picture QA' : 'Picture manifest'}
          </button>
        ))}
      </div>

      {pictureTab === 'timeline' ? (
        <div className="phase-assembly-layout">
          <section className="phase-monitor" aria-label="Picture-lock preview">
            <div>
              <span aria-hidden="true">▶</span>
              <b>Canonical picture preview</b>
              <p>No project-scoped stitched video is presented unless a real picture-lock artifact is recorded.</p>
            </div>
            <footer>
              <span>00:00:00</span>
              <i aria-hidden="true" />
              <span>{formatDuration(planned || workspace?.targetDurationSec || 0)}</span>
            </footer>
          </section>
          <section className="phase-timeline" aria-label="Picture assembly timeline">
            <header className="phase-subheading">
              <div>
                <span>PICTURE ASSEMBLY</span>
                <h4>Selected video segments and continuity joins</h4>
                <p>
                  Timeline geometry is derived from planned shot durations. Audio generation and final AV delivery remain Phase 8 responsibilities.
                </p>
              </div>
              <b>{shots.length ? `${shots.length} planned` : 'Empty'}</b>
            </header>
            <div>
              <b>VIDEO</b>
              <section aria-label="Video clips by planned duration">
                {shots.length ? shots.map((row) => {
                  const duration = Math.max(1, Number(row.shot.duration_sec || 1))
                  return (
                    <span
                      key={row.shot.id}
                      style={{ flexGrow: duration }}
                      title={`${row.code} · ${duration}s · selected clip not recorded`}
                    >
                      {row.code}
                    </span>
                  )
                }) : <span>No project-scoped video segments</span>}
              </section>
            </div>
          </section>
        </div>
      ) : null}

      {pictureTab === 'review' ? (
        <section className="phase-final-qa" aria-label="Picture QA review">
          <header className="phase-subheading">
            <div>
              <span>PICTURE QA</span>
              <h4>Video integrity before picture lock</h4>
              <p>All checks remain pending until selected clips, probe evidence, and a canonical picture artifact exist.</p>
            </div>
            <span className="status-pill" data-status={qaState === 'passed' ? 'complete' : 'draft'}>
              {qaState.replaceAll('_', ' ')}
            </span>
          </header>
          <div className="phase-qa-grid">
            {[
              ['Shot coverage', 'Every planned shot has a selected, decodable video segment.'],
              ['Continuity', 'Identity, geography, motion, and joins remain coherent.'],
              ['Motion quality', 'No black frames, freezes, severe flicker, or unacceptable blur.'],
              ['Picture profile', 'Codec, dimensions, pixel format, frame rate, and time base are compatible.'],
              ['Picture duration', 'The canonical edit matches the approved duration plan.'],
              ['Picture lock', 'The immutable output hash, EDL, probes, and source lineage are stored.'],
            ].map(([title, detail]) => (
              <article key={title}>
                <span aria-hidden="true">○</span>
                <div><b>{title}</b><p>{detail}</p></div>
                <small>Pending evidence</small>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {pictureTab === 'manifest' ? (
        <section className="phase-manifest-preview" aria-label="Picture manifest and provenance">
          <header className="phase-subheading">
            <div>
              <span>PICTURE MANIFEST</span>
              <h4>Canonical edit and generation lineage</h4>
              <p>This preview does not claim that video segments or a stitched picture artifact exist.</p>
            </div>
            <span className="status-pill" data-status={pictureLocked ? 'ready' : 'draft'}>
              {historical ? 'Snapshot' : 'Template'}
            </span>
          </header>
          <div className="phase-manifest-grid">
            {[
              ['Profile selection', `${profile.label} · ${profile.detail}`],
              ['Stitch policy', `${stitch.label} · ${stitch.detail}`],
              ['Selected segments', 'Workflow, model, seed, prompt, input, and output hashes'],
              ['Canonical EDL', 'Ordered segments, trims, transitions, and timebase'],
              ['Picture artifact', 'Codec, resolution, FPS, frame count, duration, SHA-256'],
              ['Video QA', 'Decode, continuity, motion, and compatibility evidence'],
            ].map(([title, detail]) => (
              <article key={title}>
                <span>{title}</span>
                <p>{detail}</p>
                <code>Awaiting picture-lock evidence</code>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {!historical ? (
        <section className="phase-final-qa" aria-label="Add an existing video source">
          <header className="phase-subheading">
            <div>
              <span>MANAGED VIDEO INGEST</span>
              <h4>Add an existing or soundless video</h4>
              <p>
                MP4, MOV, MKV, and WebM uploads are streamed into managed project
                storage, hashed, probed, and preserved unchanged. Full decode is
                still required before picture lock.
              </p>
            </div>
            <span
              className="status-pill"
              data-status={videoUploadState === 'complete' ? 'complete' : 'draft'}
            >
              {videoUploadState}
            </span>
          </header>
          <div className="phase-footer-actions">
            <input
              aria-label="Choose an existing video"
              type="file"
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm"
              onChange={(event) => {
                setVideoFile(event.target.files?.[0] ?? null)
                setVideoUploadState('idle')
                setVideoUploadMessage('')
              }}
            />
            <button
              type="button"
              className="btn primary"
              disabled={!videoFile || videoUploadState === 'uploading'}
              onClick={() => void uploadVideoSource()}
            >
              {videoUploadState === 'uploading' ? 'Uploading…' : 'Add video source'}
            </button>
          </div>
          {videoUploadMessage ? <p role="status">{videoUploadMessage}</p> : null}
        </section>
      ) : null}

      <div className="phase-footer">
        <div>
          <span>PHASE BOUNDARY</span>
          <b>Picture lock is the only handoff to Phase 8</b>
          <p>Foley, narration mixing, subtitles, final mux, and delivery QA are not performed here.</p>
        </div>
        {onNavigate ? (
          <div className="phase-footer-actions">
            <button type="button" className="btn secondary" onClick={() => onNavigate('workflows')}>
              {editorLabel('Review workflows', historical)}
            </button>
            <button type="button" className="btn primary" onClick={() => onNavigate('exports')}>
              {editorLabel('Open Exports', historical)}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function PhaseEightPreview({
  phase,
  workspace,
  historical,
  productionProfileKey,
  stitchStage,
  onNavigate,
}: PreviewProps) {
  const scenes = useMemo(() => buildSceneRows(workspace), [workspace])
  const shots = useMemo(() => buildShotRows(scenes), [scenes])
  const plannedFromShots = shots.reduce((total, row) => total + Number(row.shot.duration_sec || 0), 0)
  const audioDelivery = workspace?.audioDelivery ?? workspace?.assembly
  const planned = Number(audioDelivery?.planned_runtime_sec ?? plannedFromShots)
  const [assemblyTab, setAssemblyTab] = useState<'timeline' | 'review' | 'manifest'>('timeline')
  const qaState = String(audioDelivery?.qa_state || 'not_evaluated')
  const manifest = (audioDelivery?.manifest && typeof audioDelivery.manifest === 'object')
    ? audioDelivery.manifest as Record<string, unknown>
    : null
  const voiceShots = shots.filter((row) => row.shot.narration_text)
  const finalPresent = Boolean(audioDelivery?.final_output)
  const endLabel = formatDuration(planned || workspace?.targetDurationSec || 0)
  const picture = workspace?.picture
  const profile = productionProfilePresentation(
    historical ? String(picture?.production_profile_key || '') : productionProfileKey,
  )
  const stitch = stitchStagePresentation(
    historical ? String(picture?.stitch_stage || '') : stitchStage,
  )

  return (
    <div className="phase-workspace">
      <PhasePreviewHeader
        phase={phase}
        historical={historical}
        source={historical ? 'Retained snapshot' : 'Design template'}
        description="Generate Foley against the canonical picture, mix narration, music, and effects, optionally perform the deferred stitch, then validate the final synchronized delivery artifact."
        actions={[{ label: 'Workflows', page: 'workflows' }, { label: 'Exports', page: 'exports' }]}
        onNavigate={onNavigate}
      />
      <PreviewDisclosure historical={historical} />
      <div className="phase-metrics five">
        <WorkspaceMetric label="Production profile" value={profile.label} detail={profile.detail} />
        <WorkspaceMetric label="Stitch stage" value={stitch.label} detail={stitch.detail} />
        <WorkspaceMetric
          label="Delivery runtime"
          value={planned ? formatDuration(planned) : '—'}
          detail={workspace ? `${formatDuration(workspace.targetDurationSec)} target` : undefined}
        />
        <WorkspaceMetric
          label="Final output"
          value={finalPresent ? 'Present' : 'Not produced'}
        />
        <WorkspaceMetric label="Final QA" value={qaState.replaceAll('_', ' ')} />
      </div>

      <div className="phase-inline-tabs phase-major-tabs" role="tablist" aria-label="Phase 8 audio and delivery view">
        {(['timeline', 'review', 'manifest'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={assemblyTab === tab}
            className={assemblyTab === tab ? 'active' : ''}
            onClick={() => setAssemblyTab(tab)}
          >
            {tab === 'timeline' ? 'Audio timeline' : tab === 'review' ? 'Delivery QA' : 'Delivery manifest'}
          </button>
        ))}
      </div>

      {assemblyTab === 'timeline' ? (
        <div className="phase-assembly-layout">
          <section className="phase-monitor" aria-label="Final audio delivery preview">
            <div>
              <span aria-hidden="true">▶</span>
              <b>Final preview area</b>
              <p>
                {finalPresent
                  ? 'A final_output reference is recorded, but no project-scoped player stream is wired.'
                  : `No final synchronized delivery is available${historical ? ' in this snapshot' : ''}.`}
              </p>
            </div>
            <footer>
              <span>00:00:00</span>
              <i aria-hidden="true" />
              <span>{endLabel}</span>
            </footer>
          </section>

          <section className="phase-timeline" aria-label="Audio and delivery timeline tracks">
            <header className="phase-subheading">
              <div>
                <span>AUDIO & DELIVERY TIMELINE</span>
                <h4>Locked picture, voice, Foley, music, and subtitle tracks</h4>
                <p>
                  Timeline geometry is derived from {historical ? 'snapshot' : 'planned'} shot durations only.
                  No audio, mux, or deferred stitch is presented without project-scoped artifacts.
                </p>
              </div>
              <b>{shots.length ? `${shots.length} planned` : 'Empty'}</b>
            </header>

            <div>
              <b>PICTURE</b>
              <section aria-label="Video clips by planned duration">
                {shots.length ? shots.map((row) => {
                  const dur = Math.max(1, Number(row.shot.duration_sec || 1))
                  return (
                    <span
                      key={row.shot.id}
                      style={{ flexGrow: dur }}
                      title={`${row.code} · ${dur}s · clip not generated`}
                    >
                      {row.code}
                    </span>
                  )
                }) : <span>No immutable picture-lock reference</span>}
              </section>
            </div>

            <div className={voiceShots.length ? 'audio' : 'audio empty'}>
              <b>VOICE</b>
              <section aria-label="Voice clips">
                {voiceShots.length ? voiceShots.map((row) => {
                  const dur = Math.max(1, Number(row.shot.duration_sec || 1))
                  return (
                    <span
                      key={row.shot.id}
                      style={{ flexGrow: dur }}
                      title={`${row.code} · narration planned, audio not synthesized`}
                    >
                      {row.code}
                    </span>
                  )
                }) : <span>Narration lane — no voice assets generated</span>}
              </section>
            </div>

            <div className="empty">
              <b>FOLEY / MUSIC</b>
              <section><span>Foley, ambience, music, and SFX design lane</span></section>
            </div>
            <div className="empty">
              <b>CAPTIONS</b>
              <section><span>Subtitle and accessibility lane</span></section>
            </div>
          </section>
        </div>
      ) : null}

      {assemblyTab === 'review' ? (
        <section className="phase-final-qa" aria-label="Delivery QA review">
          <header className="phase-subheading">
            <div>
              <span>DELIVERY QA REVIEW</span>
              <h4>Audio synchronization and final technical validation</h4>
              <p>
                Every check remains pending until real project-scoped outputs and probe evidence exist.
                No FFmpeg or decode validation is run from this UI.
              </p>
            </div>
            <span className="status-pill" data-status={qaState === 'passed' ? 'complete' : 'draft'}>
              {qaState.replaceAll('_', ' ')}
            </span>
          </header>
          <div className="phase-qa-grid">
            {[
              ['Picture-lock identity', 'The final mux consumes the approved immutable Phase 7 picture hash.'],
              ['Foley coverage', 'Every planned sound window has a generated or approved exception result.'],
              ['Mix integrity', 'Narration, Foley, music, ambience, and effects remain intelligible and balanced.'],
              ['Audio sync', 'Narration and dialogue align with picture and remain intelligible.'],
              ['Delivery profile', 'Picture and audio codecs, duration, FPS, sample rate, and loudness are verified.'],
              ['Output integrity', 'Final decode, SHA-256, manifest, and provenance are stored.'],
            ].map(([title, detail]) => (
              <article key={title}>
                <span aria-hidden="true">○</span>
                <div>
                  <b>{title}</b>
                  <p>{detail}</p>
                </div>
                <small>Pending evidence</small>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {assemblyTab === 'manifest' ? (
        <section className="phase-manifest-preview" aria-label="Delivery manifest and provenance">
          <header className="phase-subheading">
            <div>
              <span>DELIVERY MANIFEST</span>
              <h4>Final AV provenance and delivery record</h4>
              <p>
                {manifest
                  ? `Snapshot manifest schema: ${String(manifest.schema || 'unknown')}`
                  : 'This schema preview does not claim that an output exists.'}
              </p>
            </div>
            <span className="status-pill" data-status={manifest ? 'ready' : 'draft'}>
              {historical ? 'Snapshot' : 'Template'}
            </span>
          </header>
          <div className="phase-manifest-grid">
            {[
              ['Output identity', 'Canonical filename, delivery path, SHA-256'],
              ['Picture profile', 'Codec, resolution, aspect ratio, FPS, frame count'],
              ['Audio profile', 'Codec, channels, sample rate, loudness, duration'],
              ['Source lineage', 'Picture-lock hash, audio windows, prompts, models, workflows, seeds'],
              ['Post-production', 'Foley, mixing, mux, normalization, subtitles'],
              ['Review history', 'Candidate decisions, retries, QA reports, approvals'],
            ].map(([title, detail]) => (
              <article key={title}>
                <span>{title}</span>
                <p>{detail}</p>
                <code>{manifest?.note ? String(manifest.note) : 'Awaiting production output'}</code>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <div className="phase-footer">
        <div>
          <span>DELIVERY BOUNDARY</span>
          <b>Final completion requires project-scoped AV evidence</b>
          <p>No Foley, mix, mux, deferred stitch, or final-output state is represented as complete without backend evidence.</p>
        </div>
        {onNavigate ? (
          <div className="phase-footer-actions">
            <button type="button" className="btn secondary" onClick={() => onNavigate('workflows')}>
              {editorLabel('Review workflows', historical)}
            </button>
            <button type="button" className="btn primary" onClick={() => onNavigate('exports')}>
              {editorLabel('Open Exports', historical)}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function ProductionPhasePreview({
  phase,
  workspace,
  historical,
  incompleteReason,
  productionProfileKey,
  stitchStage,
  onNavigate,
}: PreviewProps) {
  if (historical && incompleteReason) {
    return (
      <div className="phase-workspace">
        <PhasePreviewHeader
          phase={phase}
          historical
          source="Retained snapshot"
          description="This retained iteration cannot reconstruct the phase workspace from its stored snapshot alone."
        />
        <IncompleteSnapshotState phaseNumber={phase.phase_number} reason={incompleteReason} />
      </div>
    )
  }

  if (historical && !workspace) {
    return (
      <div className="phase-workspace">
        <PhasePreviewHeader
          phase={phase}
          historical
          source="Retained snapshot"
          description="No verified snapshot workspace is available for this iteration."
        />
        <IncompleteSnapshotState
          phaseNumber={phase.phase_number}
          reason="The verified historical workspace is unavailable. Current draft data was not substituted."
        />
      </div>
    )
  }

  switch (phase.phase_number) {
    case 2:
      return <PhaseTwoPreview phase={phase} workspace={workspace} historical={historical} onNavigate={onNavigate} />
    case 3:
      return <PhaseThreePreview phase={phase} workspace={workspace} historical={historical} onNavigate={onNavigate} />
    case 4:
      return <PhaseFourPreview phase={phase} workspace={workspace} historical={historical} onNavigate={onNavigate} />
    case 5:
      return <PhaseFivePreview phase={phase} workspace={workspace} historical={historical} onNavigate={onNavigate} />
    case 6:
      return <PhaseSixPreview phase={phase} workspace={workspace} historical={historical} onNavigate={onNavigate} />
    case 7:
      return (
        <PhaseSevenPreview
          phase={phase}
          workspace={workspace}
          historical={historical}
          productionProfileKey={productionProfileKey}
          stitchStage={stitchStage}
          onNavigate={onNavigate}
        />
      )
    case 8:
      return (
        <PhaseEightPreview
          phase={phase}
          workspace={workspace}
          historical={historical}
          productionProfileKey={productionProfileKey}
          stitchStage={stitchStage}
          onNavigate={onNavigate}
        />
      )
    default:
      return (
        <div className="panel">
          <div className="panel-title">
            <div>
              <span className="eyebrow">PHASE {phase.phase_number}</span>
              <h2>{phase.name}</h2>
              <p>No dedicated workspace preview is registered for this phase number.</p>
            </div>
          </div>
        </div>
      )
  }
}
