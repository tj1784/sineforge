/**
 * Immutable production-phase snapshot adapters for historical rendering.
 * Historical UI must use only verified snapshot payloads — never live aggregate.
 */

import type { PhaseVersionDetail, StoryboardAggregate } from '../api/client'

export type SnapshotSourceMode = 'current' | 'historical'

export type SnapshotCompleteness = {
  complete: boolean
  phaseNumber: number
  missingDomains: string[]
  schemaVersion: number | null
  reason: string | null
}

export type SnapshotChapter = {
  id: string
  title: string
  summary?: string | null
  order_index?: number
}

export type SnapshotScene = {
  id: string
  chapter_id?: string | null
  title: string
  summary?: string | null
  location?: string | null
  order_index?: number
  duration_sec?: number
}

export type SnapshotShot = {
  id: string
  scene_id?: string | null
  title: string
  story_purpose?: string | null
  visual_description?: string | null
  duration_sec?: number | null
  location?: string | null
  order_index?: number
  approval_state?: string | null
  production_status?: string | null
  continuity_source_type?: string
  continuity_source_shot_id?: string | null
  starting_image_asset_id?: string | null
  starting_image_required?: boolean
  camera_direction?: string | null
  motion_direction?: string | null
  characters?: Array<{ character_id: string; role_in_shot?: string | null; order_index?: number }>
  image_prompt?: string | null
  video_prompt?: string | null
  negative_prompt?: string | null
  narration_text?: string | null
  voice_profile_id?: string | null
}

export type SnapshotCharacter = {
  id: string
  name: string
  role?: string | null
  physical_description?: string | null
  age_range?: string | null
  personality?: string | null
  speaking_style?: string | null
  wardrobe?: string | null
  consistency_prompt?: string | null
  approval_state?: string | null
  reference_links?: Array<{
    id: string
    asset_id?: string | null
    reference_role?: string | null
    approved?: boolean
    order_index?: number
  }>
  assigned_voice_profile_id?: string | null
}

export type SnapshotVoice = {
  id: string
  name: string
  character_id?: string | null
  setup_mode?: string | null
  provider?: string | null
  language?: string | null
  consent_confirmed?: boolean
  approval_state?: string | null
  tone?: string | null
  design_description?: string | null
}

export type SnapshotMediaRef = {
  id: string
  kind?: string | null
  managed_uri?: string | null
  content_hash?: string | null
  original_filename?: string | null
  width?: number | null
  height?: number | null
  approval_state?: string | null
}

export type SnapshotWorkspace = {
  phaseNumber: number
  storyId: string
  projectId: string
  narrative: Record<string, unknown> | null
  chapters: SnapshotChapter[]
  scenes: SnapshotScene[]
  shots: SnapshotShot[]
  characters: SnapshotCharacter[]
  voices: SnapshotVoice[]
  locations: string[]
  keyAssets: unknown[]
  promptPackages: Array<Record<string, unknown>>
  taskAssignments: Array<Record<string, unknown>>
  providerProfiles: Array<Record<string, unknown>>
  planningMedia: SnapshotMediaRef[]
  picture: Record<string, unknown> | null
  audioDelivery: Record<string, unknown> | null
  /** Phase-scoped compatibility view: picture for Phase 7, audio delivery for Phase 8. */
  assembly: Record<string, unknown> | null
  targetDurationSec: number
  completeness: SnapshotCompleteness
}

const REQUIRED_DOMAINS: Record<number, string[]> = {
  1: ['narrative'],
  2: ['structure'],
  3: ['identity'],
  4: ['locations'],
  5: ['prompts'],
  6: ['media'],
  7: ['picture'],
  8: ['audio_delivery'],
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function num(value: unknown, fallback = 0): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export function requiredDomainsForPhase(phaseNumber: number): string[] {
  return REQUIRED_DOMAINS[phaseNumber] ?? []
}

export function assessSnapshotCompleteness(
  output: Record<string, unknown> | null | undefined,
  phaseNumber: number,
): SnapshotCompleteness {
  if (!output) {
    return {
      complete: false,
      phaseNumber,
      missingDomains: requiredDomainsForPhase(phaseNumber),
      schemaVersion: null,
      reason: 'Snapshot payload is missing.',
    }
  }
  const schemaVersion = num(output.snapshot_schema_version, 0) || null
  if (output.schema_name !== 'cineforge.production_phase_snapshot' && phaseNumber !== 1) {
    // Phase 1 may store a script package instead of the phase snapshot envelope.
    if (!(phaseNumber === 1 && output.schema_name === 'cineforge.phase_one_script_package')) {
      return {
        complete: false,
        phaseNumber,
        missingDomains: requiredDomainsForPhase(phaseNumber),
        schemaVersion,
        reason: 'Unsupported or legacy snapshot schema.',
      }
    }
  }
  if (phaseNumber === 1) {
    const isPackage = output.schema_name === 'cineforge.phase_one_script_package'
    const hasNarrative = Boolean(asRecord(output.narrative))
    if (isPackage || hasNarrative) {
      return {
        complete: true,
        phaseNumber,
        missingDomains: [],
        schemaVersion: schemaVersion ?? 1,
        reason: null,
      }
    }
    return {
      complete: false,
      phaseNumber,
      missingDomains: ['narrative'],
      schemaVersion,
      reason: 'Legacy snapshot is incomplete for Phase 1 narrative content.',
    }
  }
  const requiredDomains = requiredDomainsForPhase(phaseNumber)
  const legacyPhaseSeven =
    phaseNumber === 7 &&
    schemaVersion === 1 &&
    Boolean(asRecord(output.assembly))
  const missing = legacyPhaseSeven
    ? []
    : requiredDomains.filter((domain) => !asRecord(output[domain]))
  if (missing.length) {
    return {
      complete: false,
      phaseNumber,
      missingDomains: missing,
      schemaVersion,
      reason: `Legacy snapshot is incomplete (missing: ${missing.join(', ')}).`,
    }
  }
  return {
    complete: true,
    phaseNumber,
    missingDomains: [],
    schemaVersion: schemaVersion ?? 1,
    reason: null,
  }
}

export function validateHistoricalDetail(
  detail: PhaseVersionDetail,
  expected: { storyId: string; projectId?: string; phaseNumber: number },
): string | null {
  if (detail.verified === false) return 'The retained iteration failed integrity verification.'
  if (detail.story_id !== expected.storyId) return 'The retained iteration belongs to a different story.'
  if (expected.projectId && detail.project_id !== expected.projectId) {
    return 'The retained iteration belongs to a different project.'
  }
  if (detail.phase_number !== expected.phaseNumber) {
    return 'The retained iteration belongs to a different production phase.'
  }
  if (
    detail.snapshot_schema_version != null &&
    ![1, 2].includes(detail.snapshot_schema_version)
  ) {
    return `Unsupported snapshot schema version ${detail.snapshot_schema_version}.`
  }
  if (!detail.output_hash || !/^[a-f0-9]{64}$/i.test(detail.output_hash)) {
    return 'The retained iteration is missing a valid content hash.'
  }
  return null
}

function mapShotsFromStructure(
  structure: Record<string, unknown>,
  prompts: Record<string, unknown> | null,
  media: Record<string, unknown> | null,
): SnapshotShot[] {
  const packages = asArray(prompts?.prompt_packages)
  const packageByShot = new Map<string, Record<string, unknown>>()
  for (const item of packages) {
    const row = asRecord(item)
    if (!row) continue
    const shotId = str(row.shot_id)
    if (shotId && !packageByShot.has(shotId)) packageByShot.set(shotId, row)
  }
  const narrations = asArray(media?.narrations)
  const narrationByShot = new Map<string, Record<string, unknown>>()
  for (const item of narrations) {
    const row = asRecord(item)
    if (!row) continue
    const shotId = str(row.shot_id)
    if (shotId) narrationByShot.set(shotId, row)
  }
  const cast = asArray(media?.shot_character_links)
  const castByShot = new Map<string, SnapshotShot['characters']>()
  for (const item of cast) {
    const row = asRecord(item)
    if (!row) continue
    const shotId = str(row.shot_id)
    if (!shotId) continue
    const list = castByShot.get(shotId) ?? []
    list.push({
      character_id: str(row.character_id),
      role_in_shot: str(row.role_in_shot) || null,
      order_index: num(row.order_index),
    })
    castByShot.set(shotId, list)
  }

  return asArray(structure.shots).map((item) => {
    const row = asRecord(item) ?? {}
    const id = str(row.id)
    const pkg = packageByShot.get(id)
    const narration = narrationByShot.get(id)
    return {
      id,
      scene_id: str(row.scene_id) || null,
      title: str(row.title, 'Untitled shot'),
      story_purpose: str(row.story_purpose) || null,
      visual_description: str(row.visual_description) || null,
      duration_sec: row.duration_sec == null ? null : num(row.duration_sec),
      location: str(row.location) || null,
      order_index: num(row.order_index),
      approval_state: str(row.approval_state) || null,
      production_status: str(row.production_status) || null,
      continuity_source_type: str(row.continuity_source_type, 'none'),
      continuity_source_shot_id: str(row.continuity_source_shot_id) || null,
      starting_image_asset_id: str(row.starting_image_asset_id) || null,
      starting_image_required: Boolean(row.starting_image_asset_id) || Boolean(row.starting_image_required),
      camera_direction: str(row.camera_direction) || null,
      motion_direction: str(row.motion_direction) || null,
      characters: castByShot.get(id) ?? [],
      image_prompt: str(pkg?.image_prompt) || null,
      video_prompt: str(pkg?.video_prompt) || null,
      negative_prompt: str(pkg?.negative_prompt) || null,
      narration_text: str(narration?.narration_text) || null,
      voice_profile_id: str(narration?.voice_profile_id) || null,
    }
  })
}

export function workspaceFromHistoricalDetail(
  detail: PhaseVersionDetail,
  expected: { storyId: string; projectId?: string; phaseNumber: number },
): { workspace: SnapshotWorkspace | null; error: string | null } {
  const isolationError = validateHistoricalDetail(detail, expected)
  if (isolationError) return { workspace: null, error: isolationError }

  const output = asRecord(detail.output_json) ?? {}
  const completeness = assessSnapshotCompleteness(output, expected.phaseNumber)
  if (!completeness.complete) {
    return {
      workspace: {
        phaseNumber: expected.phaseNumber,
        storyId: detail.story_id,
        projectId: detail.project_id,
        narrative: null,
        chapters: [],
        scenes: [],
        shots: [],
        characters: [],
        voices: [],
        locations: [],
        keyAssets: [],
        promptPackages: [],
        taskAssignments: [],
        providerProfiles: [],
        planningMedia: [],
        picture: null,
        audioDelivery: null,
        assembly: null,
        targetDurationSec: 0,
        completeness,
      },
      error: null,
    }
  }

  const narrative = asRecord(output.narrative)
  const structure = asRecord(output.structure) ?? {}
  const identity = asRecord(output.identity) ?? {}
  const locationsDomain = asRecord(output.locations) ?? {}
  const prompts = asRecord(output.prompts)
  const media = asRecord(output.media)
  const legacyAssembly = asRecord(output.assembly)
  const picture = asRecord(output.picture) ?? (
    expected.phaseNumber === 7 ? legacyAssembly : null
  )
  const audioDelivery = asRecord(output.audio_delivery)
  const assembly = expected.phaseNumber === 8
    ? audioDelivery
    : picture ?? legacyAssembly

  const chapters = asArray(structure.chapters).map((item) => {
    const row = asRecord(item) ?? {}
    return {
      id: str(row.id),
      title: str(row.title, 'Untitled chapter'),
      summary: str(row.summary) || null,
      order_index: num(row.order_index),
    }
  })
  const scenes = asArray(structure.scenes).map((item) => {
    const row = asRecord(item) ?? {}
    return {
      id: str(row.id),
      chapter_id: str(row.chapter_id) || null,
      title: str(row.title, 'Untitled scene'),
      summary: str(row.summary) || null,
      location: str(row.location) || null,
      order_index: num(row.order_index),
    }
  })
  const shots = mapShotsFromStructure(structure, prompts, media)

  const refLinks = asArray(identity.character_reference_links)
  const refsByCharacter = new Map<string, SnapshotCharacter['reference_links']>()
  for (const item of refLinks) {
    const row = asRecord(item) ?? {}
    const characterId = str(row.character_id)
    if (!characterId) continue
    const list = refsByCharacter.get(characterId) ?? []
    list.push({
      id: str(row.id),
      asset_id: str(row.asset_id) || null,
      reference_role: str(row.reference_role) || null,
      approved: Boolean(row.approved),
      order_index: num(row.order_index),
    })
    refsByCharacter.set(characterId, list)
  }

  const characters = asArray(identity.characters).map((item) => {
    const row = asRecord(item) ?? {}
    const id = str(row.id)
    return {
      id,
      name: str(row.name, 'Unnamed character'),
      role: str(row.role) || null,
      physical_description: str(row.physical_description) || null,
      age_range: str(row.age_range) || null,
      personality: str(row.personality) || null,
      speaking_style: str(row.speaking_style) || null,
      wardrobe: str(row.wardrobe) || null,
      consistency_prompt: str(row.consistency_prompt) || null,
      approval_state: str(row.approval_state) || null,
      reference_links: refsByCharacter.get(id) ?? [],
      assigned_voice_profile_id: null as string | null,
    }
  })

  const voices = asArray(identity.voices).map((item) => {
    const row = asRecord(item) ?? {}
    return {
      id: str(row.id),
      name: str(row.name, 'Voice'),
      character_id: str(row.character_id) || null,
      setup_mode: str(row.setup_mode) || null,
      provider: str(row.provider) || null,
      language: str(row.language) || null,
      consent_confirmed: Boolean(row.consent_confirmed),
      approval_state: str(row.approval_state) || null,
    }
  })
  for (const voice of voices) {
    if (!voice.character_id) continue
    const character = characters.find((item) => item.id === voice.character_id)
    if (character && !character.assigned_voice_profile_id) {
      character.assigned_voice_profile_id = voice.id
    }
  }

  const locations = asArray(locationsDomain.locations).map((item) => str(item)).filter(Boolean)
  const planningMedia = asArray(media?.planning_media).map((item) => {
    const row = asRecord(item) ?? {}
    return {
      id: str(row.id),
      kind: str(row.kind) || null,
      managed_uri: str(row.managed_uri) || null,
      content_hash: str(row.content_hash) || null,
      original_filename: str(row.original_filename) || null,
      width: row.width == null ? null : num(row.width),
      height: row.height == null ? null : num(row.height),
      approval_state: str(row.approval_state) || null,
    }
  })

  return {
    workspace: {
      phaseNumber: expected.phaseNumber,
      storyId: detail.story_id,
      projectId: detail.project_id,
      narrative,
      chapters,
      scenes,
      shots,
      characters,
      voices,
      locations,
      keyAssets: asArray(locationsDomain.key_assets),
      promptPackages: asArray(prompts?.prompt_packages).map((item) => asRecord(item) ?? {}),
      taskAssignments: asArray(prompts?.task_assignments).map((item) => asRecord(item) ?? {}),
      providerProfiles: asArray(prompts?.provider_profiles).map((item) => asRecord(item) ?? {}),
      planningMedia,
      picture,
      audioDelivery,
      assembly,
      targetDurationSec: num(narrative?.target_duration_sec),
      completeness,
    },
    error: null,
  }
}

export function workspaceFromAggregate(
  data: StoryboardAggregate,
  phaseNumber: number,
): SnapshotWorkspace {
  const chapters: SnapshotChapter[] = data.chapters.map((chapter, index) => ({
    id: chapter.id,
    title: chapter.title,
    summary: chapter.summary,
    order_index: index,
  }))
  const scenes: SnapshotScene[] = []
  const shots: SnapshotShot[] = []
  data.chapters.forEach((chapter) => {
    chapter.scenes.forEach((scene) => {
      scenes.push({
        id: scene.id,
        chapter_id: chapter.id,
        title: scene.title,
        summary: scene.summary,
        location: null,
        order_index: scene.order_index,
        duration_sec: Number(scene.duration_sec ?? 0),
      })
      scene.shots.forEach((shot) => {
        shots.push({
          id: shot.id,
          scene_id: scene.id,
          title: shot.title,
          story_purpose: shot.story_purpose,
          visual_description: shot.visual_description,
          duration_sec: Number(shot.duration_sec ?? 0),
          location: shot.location,
          order_index: shot.order_index,
          approval_state: shot.approval_state,
          production_status: shot.production_status,
          continuity_source_type: shot.continuity_source_type,
          continuity_source_shot_id: shot.continuity_source_shot_id,
          starting_image_asset_id: shot.starting_image_asset_id,
          starting_image_required: shot.starting_image_required,
          camera_direction: shot.camera_direction,
          motion_direction: shot.motion_direction,
          characters: (shot.characters ?? []).map((link) => ({
            character_id: link.character_id,
            role_in_shot: link.role_in_shot,
            order_index: link.order_index,
          })),
          image_prompt: shot.prompt_positive,
          video_prompt: shot.prompt_video,
          negative_prompt: shot.prompt_negative,
          narration_text: shot.narration,
          voice_profile_id: shot.narration_voice_profile_id,
        })
      })
    })
  })

  const locations = [...new Set(shots.map((shot) => shot.location).filter(Boolean) as string[])]

  return {
    phaseNumber,
    storyId: data.story.id,
    projectId: data.story.project_id,
    narrative: {
      title: data.story.title,
      base_story: data.story.base_story,
      logline: data.story.logline,
      synopsis: data.story.synopsis,
      target_duration_sec: data.story.target_duration_sec,
      visual_style: data.story.visual_style,
    },
    chapters,
    scenes,
    shots,
    characters: data.characters.map((character) => ({
      id: character.id,
      name: character.name,
      role: character.role,
      physical_description: character.physical_description,
      age_range: character.age_range,
      personality: character.personality,
      speaking_style: character.speaking_style,
      wardrobe: character.wardrobe,
      consistency_prompt: character.consistency_prompt,
      approval_state: character.approval_state,
      reference_links: (character.reference_assets ?? []).map((ref) => ({
        id: ref.id,
        asset_id: ref.asset_id,
        reference_role: ref.reference_role,
        approved: ref.approved,
        order_index: ref.order_index,
      })),
      assigned_voice_profile_id: character.assigned_voice_profile_id,
    })),
    voices: data.voices.map((voice) => ({
      id: voice.id,
      name: voice.name,
      character_id: voice.character_id,
      setup_mode: voice.setup_mode,
      provider: voice.provider,
      language: voice.language,
      consent_confirmed: voice.consent_confirmed,
      approval_state: voice.approval_state,
      tone: voice.tone,
      design_description: voice.design_description,
    })),
    locations,
    keyAssets: [],
    promptPackages: [],
    taskAssignments: [],
    providerProfiles: [],
    planningMedia: [],
    picture: {
      planned_shot_count: shots.length,
      planned_runtime_sec: shots.reduce((total, shot) => total + Number(shot.duration_sec || 0), 0),
      picture_locked: false,
      picture_lock: null,
      canonical_edl: null,
      qa_state: 'not_evaluated',
    },
    audioDelivery: {
      picture_lock_required: true,
      foley_windows: [],
      stems: [],
      mix_master: null,
      final_output: null,
      delivery_ready: false,
      qa_state: 'not_evaluated',
    },
    assembly: phaseNumber === 8
      ? {
          picture_lock_required: true,
          foley_windows: [],
          stems: [],
          mix_master: null,
          final_output: null,
          delivery_ready: false,
          qa_state: 'not_evaluated',
        }
      : {
          planned_shot_count: shots.length,
          planned_runtime_sec: shots.reduce(
            (total, shot) => total + Number(shot.duration_sec || 0),
            0,
          ),
          picture_locked: false,
          picture_lock: null,
          canonical_edl: null,
          qa_state: 'not_evaluated',
        },
    targetDurationSec: Number(data.story.target_duration_sec || 0),
    completeness: {
      complete: true,
      phaseNumber,
      missingDomains: [],
      schemaVersion: 1,
      reason: null,
    },
  }
}

export function snapshotMetricsFromWorkspace(workspace: SnapshotWorkspace | null) {
  if (!workspace) {
    return [
      { label: 'Chapters', value: 0 },
      { label: 'Scenes', value: 0 },
      { label: 'Shots', value: 0 },
      { label: 'Characters', value: 0 },
      { label: 'Media refs', value: 0 },
    ]
  }
  return [
    { label: 'Chapters', value: workspace.chapters.length },
    { label: 'Scenes', value: workspace.scenes.length },
    { label: 'Shots', value: workspace.shots.length },
    { label: 'Characters', value: workspace.characters.length },
    { label: 'Media refs', value: workspace.planningMedia.length },
  ]
}
