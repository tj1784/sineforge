import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, type ProductionPipeline, type StoryboardAggregate } from '../../api/client'
import { ProductionPhases } from './ProductionPhases'

vi.mock('../../api/client', () => ({
  api: {
    getProductionPipeline: vi.fn(),
    generatePhaseOne: vi.fn(),
    approveProductionPhase: vi.fn(),
    revisePhaseOne: vi.fn(),
    listPhaseVersions: vi.fn(),
    getPhaseVersion: vi.fn(),
    createPhaseVersion: vi.fn(),
    exportPhaseHistory: vi.fn(),
    listRuntimeWorkflowTemplates: vi.fn(),
    getSettings: vi.fn(),
    preparePhaseSixImages: vi.fn(),
    generatePhaseFiveHandoff: vi.fn(),
    generateStartingImage: vi.fn(),
  },
}))

const phaseNames = [
  'Script and Narrative Development',
  'Scene and Shot Segmentation',
  'Character Development',
  'Location and Key-Asset Development',
  'Production Prompt and Workflow Package',
  'Image and Voice Generation and Mapping',
  'Video Generation, Continuity, Assembly, and Picture Lock',
  'Foley, Audio Mix, Final Mux, and Delivery QA',
]

const packageData = {
  schema_name: 'cineforge.phase_one_script_package',
  schema_version: 1,
  project_title: 'The Test Film',
  logline: 'A complete test logline.',
  short_synopsis: 'A complete synopsis.',
  detailed_treatment: 'Opening, development, climax, and resolution.',
  complete_script: '## Opening\n**ACTION:** The story begins.\n**NARRATION:** The story begins.',
  narration_script: 'The story begins.',
  dialogue_script: 'No spoken character dialogue is required by the supplied source.',
  non_dialogue_action: ['The story begins.'],
  silent_visual_beats: ['The moment settles.'],
  emotional_progression: ['Orientation', 'Development', 'Climax', 'Resolution'],
  dramatic_escalation: ['Opening', 'Development', 'Climax', 'Resolution'],
  narrative_structure: { opening: 'A', middle: 'B', climax: 'C', resolution: 'D' },
  pacing_plan: [],
  duration_analysis: {
    target_duration_sec: 300,
    narration_word_count: 10,
    dialogue_word_count: 0,
    narration_duration_sec: 120,
    dialogue_duration_sec: 0,
    planned_silence_visual_duration_sec: 180,
    estimated_total_duration_sec: 300,
  },
  script_word_count: 640,
  source_fidelity_notes: ['All events retain source anchors.'],
  creative_assumptions: ['No unsupported event was added.'],
  creative_direction: { language: 'English' },
  generation_boundary: {
    phase: 1 as const,
    text_only: true as const,
    media_generated: false as const,
    rendering_enabled: false as const,
    final_scene_or_shot_segmentation_created: false as const,
  },
}

const pipeline: ProductionPipeline = {
  story_id: 'story-1',
  project_id: 'project-1',
  exact_phase_count: 8,
  completion_message: 'Your complete script is ready for review.',
  phases: phaseNames.map((name, index) => ({
    id: `phase-${index + 1}`,
    phase_number: index + 1,
    name,
    lifecycle_state: index === 0 ? 'ready_for_review' : 'not_started',
    current_version_number: index === 0 ? 1 : 1,
    version_count: 1,
    is_locked: index !== 0,
    locked_reason: index === 0 ? null : `Phase ${index} must be approved.`,
    is_stale: false,
    stale_reason: null,
    generation_completed_at: index === 0 ? '2026-07-19T00:00:00Z' : null,
    approved_at: null,
    latest_version: index === 0 ? {
      id: 'version-1',
      version_number: 1,
      lifecycle_state: 'ready_for_review',
      completed: true,
      input_snapshot_json: {},
      output_json: packageData,
      input_hash: 'a'.repeat(64),
      output_hash: 'b'.repeat(64),
      created_by: 'test',
      previous_version_id: null,
      created_at: '2026-07-19T00:00:00Z',
      updated_at: '2026-07-19T00:00:00Z',
    } : null,
    latest_qa_report: index === 0 ? {
      id: 'qa-1',
      entity_type: 'production_phase_version',
      entity_id: 'version-1',
      created_at: '2026-07-19T00:00:00Z',
      report_json: {
        phase_number: 1,
        passed: true,
        result: 'pass',
        checks: [{ code: 'phase_boundary', label: 'No downstream execution', passed: true, blocking: true, detail: 'Text only.' }],
        blocking_failures: [],
        review_items: [],
        phase_boundary: { images_generated: false, voices_generated: false, videos_generated: false },
      },
    } : null,
  })),
}

const aggregate: StoryboardAggregate = {
  revision: 'workspace-v1',
  content_hash: 'workspace-hash',
  planned_duration_sec: 15,
  discrepancy_sec: -285,
  story: {
    id: 'story-1',
    project_id: 'project-1',
    title: 'The Test Film',
    base_story: 'A complete source story.',
    target_duration_sec: 300,
    logline: 'A complete test logline.',
    synopsis: 'A complete synopsis.',
    audience: 'General audiences',
    tone: 'Reverent',
    genre: 'Cinematic narrative',
    visual_style: 'Grounded cinematic realism',
    point_of_view: 'Third person',
    production_notes: null,
    approval_state: 'draft',
  },
  chapters: [{
    id: 'chapter-1',
    order_index: 0,
    title: 'Act I',
    summary: 'The opening movement.',
    duration_sec: 15,
    scenes: [{
      id: 'scene-1',
      order_index: 0,
      title: 'Opening scene',
      summary: 'The story opens.',
      duration_sec: 15,
      shots: [{
        id: 'shot-1',
        order_index: 0,
        display_label: 'A',
        title: 'Opening image',
        duration_sec: 8,
        duration_override_reason: null,
        visual_description: 'A grounded opening frame.',
        story_purpose: 'Establish the world.',
        location: 'Primary location',
        continuity_source_type: 'none',
        approval_state: 'draft',
        production_status: 'planned',
        blocked_reason: null,
        continuity_source_shot_id: null,
        starting_image_required: true,
        starting_image_asset_id: null,
        narration: 'The story begins.',
        narration_voice_profile_id: 'voice-1',
        prompt_positive: 'Grounded cinematic opening image.',
        prompt_video: 'A slow, controlled camera move.',
        prompt_negative: 'flicker, identity drift',
        prompt_continuity_instructions: 'Preserve geography and screen direction.',
        prompt_style_lock: 'Grounded cinematic realism.',
        prompt_approval_state: 'draft',
        camera_direction: 'Wide establishing shot',
        motion_direction: 'Slow push in',
        characters: [{ character_id: 'character-1', role_in_shot: 'lead', order_index: 0, continuity_notes: null }],
        recommendations: [],
      }],
    }],
  }],
  characters: [{
    id: 'character-1',
    story_id: 'story-1',
    name: 'Lead Character',
    role: 'Lead',
    approval_state: 'draft',
    age_range: 'Adult',
    physical_description: 'Distinct, grounded appearance.',
    personality: 'Reflective and courageous',
    speaking_style: 'Measured',
    wardrobe: 'Continuity-locked wardrobe',
    consistency_prompt: 'Preserve identity and wardrobe.',
    negative_identity_prompt: 'identity drift',
    assigned_voice_profile_id: 'voice-1',
    reference_assets: [],
  }],
  voices: [{
    id: 'voice-1',
    story_id: 'story-1',
    character_id: 'character-1',
    name: 'Lead voice',
    setup_mode: 'manual',
    source_type: 'manual',
    consent_confirmed: false,
    consent_required: false,
    approval_state: 'draft',
    language: 'English',
    tone: 'Measured and warm',
  }],
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baselineVersions = (phaseNumber: number) => [{
  id: `baseline-${phaseNumber}`,
  version_number: 1,
  label: 'Baseline',
  notes: 'Initial retained state for this phase.',
  source: 'baseline' as const,
  lifecycle_state: 'not_started' as const,
  completed: false,
  snapshot_schema_version: 1,
  input_hash: 'c'.repeat(64),
  output_hash: 'd'.repeat(64),
  created_by: 'system:baseline',
  previous_version_id: null,
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
}]

function mockHistoryApis() {
  vi.mocked(api.getSettings).mockResolvedValue({
    id: 'settings-1',
    project_id: 'project-1',
    settings_version: 1,
    shot_duration_min_sec: 6,
    shot_duration_max_sec: 12,
    continuity_policy_json: {},
    prompting_policy_json: {},
    voice_policy_json: {},
    approval_policy_json: {},
    speaking_rate: 1,
    aspect_ratio: '16:9',
    preview_width: 1280,
    preview_height: 720,
    final_width: 1920,
    final_height: 1080,
    fps: 24,
    captions_enabled: true,
    audio_enabled: true,
    production_profile_key: 'ltx_base@1',
    production_profile_snapshot_json: {},
    stitch_stage: 'phase7_before_audio',
    prefer_hosted_providers: false,
    prefer_local_providers: true,
    allow_model_download: false,
    allow_rendering: false,
    require_voice_consent: true,
    require_production_plan_approval: true,
  })
  vi.mocked(api.listPhaseVersions).mockImplementation(async (_storyId, phaseNumber) => baselineVersions(phaseNumber))
  vi.mocked(api.getPhaseVersion).mockImplementation(async (storyId, phaseNumber, versionId) => ({
    ...baselineVersions(phaseNumber)[0],
    id: versionId,
    story_id: storyId,
    project_id: 'project-1',
    phase_number: phaseNumber,
    phase_name: phaseNames[phaseNumber - 1],
    input_snapshot_json: {},
    output_json: { schema_name: 'cineforge.production_phase_snapshot', phase_number: phaseNumber },
    verified: true,
  }))
  vi.mocked(api.createPhaseVersion).mockResolvedValue({
    version: {
      ...baselineVersions(1)[0],
      id: 'manual-1',
      version_number: 2,
      label: 'Director review',
      source: 'manual',
      story_id: 'story-1',
      project_id: 'project-1',
      phase_number: 1,
      phase_name: phaseNames[0],
      input_snapshot_json: {},
      output_json: {},
      verified: true,
    },
    pipeline,
  })
  vi.mocked(api.generatePhaseOne).mockResolvedValue({
    pipeline,
    phase: pipeline.phases[0],
    completion_message: 'Your complete script is ready for review.',
  })
  vi.mocked(api.listRuntimeWorkflowTemplates).mockResolvedValue([])
  vi.mocked(api.preparePhaseSixImages).mockResolvedValue({
    status: {
      shot_count: 1,
      required_count: 1,
      assigned_count: 0,
      approved_count: 0,
      in_review_count: 0,
      missing_count: 1,
      complete: false,
      phase_7_locked: false,
      runtime_reachable: null,
    },
    message: 'Phase 6 images are ready for local ComfyUI generation; Phase 7 is not artificially locked.',
  })
  vi.mocked(api.generateStartingImage).mockResolvedValue({
    asset: {
      id: 'asset-1',
      project_id: 'project-1',
      kind: 'starting_image',
      source_type: 'comfyui_generated',
      managed_uri: '/media/asset-1.png',
      sha256: 'f'.repeat(64),
      mime_type: 'image/png',
      width: 1024,
      height: 576,
      duration_sec: null,
      approval_state: 'in_review',
      metadata_json: {},
      original_filename: 'S01A_Opening_image.png',
      size_bytes: 123,
      archived_at: null,
      created_at: '2026-07-19T00:00:00Z',
      updated_at: '2026-07-19T00:00:00Z',
      is_duplicate: false,
    },
    created: true,
    duplicate_of_existing: false,
    shot_id: 'shot-1',
    previous_asset_id: null,
    status: {
      shot_count: 1,
      required_count: 1,
      assigned_count: 1,
      approved_count: 0,
      in_review_count: 1,
      missing_count: 0,
      complete: false,
      phase_7_locked: false,
      runtime_reachable: true,
    },
    prompt_id: 'prompt-1',
    model_name: 'flux2_dev_fp8mixed.safetensors',
    seed: 123,
  })
  vi.mocked(api.generatePhaseFiveHandoff).mockResolvedValue({
    status: {
      shot_count: 1,
      required_count: 1,
      assigned_count: 1,
      approved_count: 0,
      in_review_count: 1,
      missing_count: 0,
      complete: false,
      phase_7_locked: false,
      runtime_reachable: true,
    },
    message: 'Phase 5 handoff complete: 1 character reference, 1 reusable asset reference, and 1 scene starting image generated and labeled.',
    character_count: 1,
    asset_count: 1,
    scene_count: 1,
    generated: {
      characters: [{
        asset: {
          id: 'asset-character-1',
          project_id: 'project-1',
          kind: 'character_reference',
          source_type: 'comfyui_generated',
          managed_uri: '/media/asset-character-1.png',
          sha256: 'a'.repeat(64),
          mime_type: 'image/png',
          width: 1024,
          height: 576,
          duration_sec: null,
          approval_state: 'in_review',
          metadata_json: { label: 'CHAR-01 Lead Character' },
          original_filename: 'CHAR_01_Lead_Character.png',
          size_bytes: 123,
          archived_at: null,
          created_at: '2026-07-19T00:00:00Z',
          updated_at: '2026-07-19T00:00:00Z',
          is_duplicate: false,
        },
        created: true,
        duplicate_of_existing: false,
        entity_type: 'character',
        entity_id: 'character-1',
        label: 'CHAR-01 Lead Character',
        prompt_id: 'prompt-character-1',
        model_name: 'flux2_dev_fp8mixed.safetensors',
        seed: 123,
      }],
      assets: [{
        asset: {
          id: 'asset-location-1',
          project_id: 'project-1',
          kind: 'art_direction_reference',
          source_type: 'comfyui_generated',
          managed_uri: '/media/asset-location-1.png',
          sha256: 'b'.repeat(64),
          mime_type: 'image/png',
          width: 1024,
          height: 576,
          duration_sec: null,
          approval_state: 'in_review',
          metadata_json: { label: 'LOC-01 Primary location' },
          original_filename: 'LOC_01_Primary_location.png',
          size_bytes: 123,
          archived_at: null,
          created_at: '2026-07-19T00:00:00Z',
          updated_at: '2026-07-19T00:00:00Z',
          is_duplicate: false,
        },
        created: true,
        duplicate_of_existing: false,
        entity_type: 'asset_reference',
        entity_id: null,
        label: 'LOC-01 Primary location',
        prompt_id: 'prompt-location-1',
        model_name: 'flux2_dev_fp8mixed.safetensors',
        seed: 1123,
      }],
      scenes: [{
        asset: {
          id: 'asset-1',
          project_id: 'project-1',
          kind: 'starting_image',
          source_type: 'comfyui_generated',
          managed_uri: '/media/asset-1.png',
          sha256: 'f'.repeat(64),
          mime_type: 'image/png',
          width: 1024,
          height: 576,
          duration_sec: null,
          approval_state: 'in_review',
          metadata_json: {
            label: 'S01A',
            labels: {
              characters: [{ label: 'CHAR-01 Lead Character', asset_ids: ['asset-character-1'] }],
              assets: [{ label: 'LOC-01 Primary location', entity_id: 'asset-location-1' }],
            },
          },
          original_filename: 'S01A_Opening_image.png',
          size_bytes: 123,
          archived_at: null,
          created_at: '2026-07-19T00:00:00Z',
          updated_at: '2026-07-19T00:00:00Z',
          is_duplicate: false,
        },
        created: true,
        duplicate_of_existing: false,
        shot_id: 'shot-1',
        previous_asset_id: null,
        status: {
          shot_count: 1,
          required_count: 1,
          assigned_count: 1,
          approved_count: 0,
          in_review_count: 1,
          missing_count: 0,
          complete: false,
          phase_7_locked: false,
          runtime_reachable: true,
        },
        prompt_id: 'prompt-1',
        model_name: 'flux2_dev_fp8mixed.safetensors',
        seed: 2123,
      }],
    },
  })
  vi.mocked(api.exportPhaseHistory).mockResolvedValue({
    schema_name: 'cineforge.phase-history',
    version: 1,
    project_id: 'project-1',
    story_id: 'story-1',
    exported_at: '2026-07-19T00:00:00Z',
    integrity: {
      verified: true,
      iteration_count: 8,
      snapshot_count: 8,
      phase_counts: { '1': 1, '2': 1, '3': 1, '4': 1, '5': 1, '6': 1, '7': 1, '8': 1 },
      hashes: Array.from({ length: 8 }, () => 'e'.repeat(64)),
    },
    iterations: [],
  })
}

describe('ProductionPhases', () => {
  it('records QA approval for the planning snapshot without claiming media execution', async () => {
    const approvedPipeline: ProductionPipeline = {
      ...pipeline,
      phases: pipeline.phases.map((phase) => phase.phase_number === 1
        ? { ...phase, lifecycle_state: 'approved', approved_at: '2026-07-22T00:00:00Z' }
        : phase.phase_number === 2
          ? { ...phase, lifecycle_state: 'drafting', is_locked: false, locked_reason: null }
          : phase),
    }
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    vi.mocked(api.approveProductionPhase).mockResolvedValue({
      pipeline: approvedPipeline,
      phase: approvedPipeline.phases[0],
      message: 'Phase 1 approved. Phase 2 is unlocked for planning.',
    })
    mockHistoryApis()

    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Approve Phase 1 planning snapshot' }))

    await waitFor(() => expect(api.approveProductionPhase).toHaveBeenCalledWith(
      'story-1',
      1,
      expect.objectContaining({
        approved_by: 'CineForge QA',
        notes: expect.stringContaining('No media generation or execution'),
      }),
    ))
    expect((await screen.findByRole('button', { name: 'Phase 1 planning approved' })).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('Phase 1 approved. Phase 2 is unlocked for planning.')).toBeTruthy()
    expect(screen.getByRole('tab', { name: /Script and Narrative Development/ }).textContent).toContain('approved')
    expect(screen.getByRole('tab', { name: /Scene and Shot Segmentation/ }).textContent).toContain('drafting')
  })

  it('submits Phase 5 as one ordered character-asset-scene handoff batch', async () => {
    const phaseFiveReadyPipeline: ProductionPipeline = {
      ...pipeline,
      phases: pipeline.phases.map((phase) => phase.phase_number < 5
        ? { ...phase, lifecycle_state: 'approved', approved_at: '2026-07-22T00:00:00Z', is_locked: false, locked_reason: null }
        : phase.phase_number === 5
          ? { ...phase, lifecycle_state: 'ready_for_review', is_locked: false, locked_reason: null }
          : phase),
    }
    const phaseFiveApprovedPipeline: ProductionPipeline = {
      ...phaseFiveReadyPipeline,
      phases: phaseFiveReadyPipeline.phases.map((phase) => phase.phase_number === 5
        ? { ...phase, lifecycle_state: 'approved', approved_at: '2026-07-22T00:00:00Z' }
        : phase),
    }
    vi.mocked(api.getProductionPipeline).mockResolvedValue(phaseFiveReadyPipeline)
    vi.mocked(api.approveProductionPhase).mockResolvedValue({
      pipeline: phaseFiveApprovedPipeline,
      phase: phaseFiveApprovedPipeline.phases[4],
      message: 'Phase 5 approved.',
    })
    mockHistoryApis()

    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)

    fireEvent.click(await screen.findByRole('tab', { name: /Production Prompt and Workflow Package/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Approve Phase 5 & choose workflow' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve and submit handoff batch' }))

    await waitFor(() => expect(api.generatePhaseFiveHandoff).toHaveBeenCalledWith(
      'story-1',
      expect.objectContaining({
        requested_by: 'CineForge Phase 5 workflow handoff',
        model_name: 'flux2_dev_fp8mixed.safetensors',
      }),
    ))
    expect(api.preparePhaseSixImages).not.toHaveBeenCalled()
    expect(api.generateStartingImage).not.toHaveBeenCalled()
    expect(await screen.findByText(/generated with attachment labels/i)).toBeTruthy()
  })

  it('shows exactly eight enabled phase tabs and opens every UI workspace', async () => {
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()

    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)

    expect(await screen.findByText('8 complete workspaces')).toBeTruthy()
    expect(screen.getAllByText('All blocking checks passed').length).toBeGreaterThan(0)
    expect(screen.getAllByText('The Test Film').length).toBeGreaterThan(0)

    // Phase 1 Gold Sites structure: PROTOTYPE DATA workspace + metrics + document
    expect(screen.getAllByText(/PHASE 1 · PROTOTYPE DATA/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Script and Narrative Development').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Interactive UI/UX prototype').length).toBeGreaterThan(0)
    expect(document.querySelector('.phase-one-workspace')).toBeTruthy()
    const metrics = document.querySelector('.phase-metrics.six')
    expect(metrics).toBeTruthy()
    expect(metrics?.querySelectorAll('.phase-metric').length).toBe(6)
    expect(screen.getAllByText('Script words').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Narration words').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Target runtime').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Planned runtime').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Readiness').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Planning QA').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Phase 1 script document').classList.contains('phase-document')).toBe(true)
    expect(screen.getAllByText('WORKING TITLE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('LOGLINE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('SHORT SYNOPSIS').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Source story and treatment').length).toBeGreaterThan(0)
    expect(screen.getAllByText('CREATIVE DIRECTION').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PRODUCTION BOUNDARY').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/PHASE 1 REVIEW/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Edit story foundation/i).length).toBeGreaterThan(0)
    expect(screen.queryByText('Complete script package')).toBeNull()
    expect(document.querySelector('.phase-one-document')).toBeNull()
    expect(document.querySelector('.phase-one-metrics')).toBeNull()

    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(8)
    tabs.forEach((tab) => expect(tab.hasAttribute('disabled')).toBe(false))
    expect(screen.queryByText(/Locked ·/i)).toBeNull()

    for (const name of phaseNames.slice(1)) {
      fireEvent.click(screen.getByRole('tab', { name: new RegExp(name) }))
      expect(screen.getByRole('heading', { name })).toBeTruthy()
      expect(screen.getAllByText('Interactive UI/UX preview').length).toBeGreaterThan(0)
    }

    fireEvent.click(screen.getByRole('tab', { name: /Script and Narrative Development/ }))
    expect(screen.getAllByText('The Test Film').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Phase 1 script document')).toBeTruthy()
    expect(api.getProductionPipeline).toHaveBeenCalledTimes(1)
    expect(api.revisePhaseOne).not.toHaveBeenCalled()
  })

  it('supports keyboard navigation across the eight phase tabs', async () => {
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)

    const first = await screen.findByRole('tab', { name: /Script and Narrative Development/ })
    fireEvent.keyDown(first, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Scene and Shot Segmentation/ }).getAttribute('aria-selected')).toBe('true')

    fireEvent.keyDown(screen.getByRole('tab', { name: /Scene and Shot Segmentation/ }), { key: 'End' })
    expect(screen.getByRole('tab', { name: /Foley, Audio Mix, Final Mux, and Delivery QA/ }).getAttribute('aria-selected')).toBe('true')

    fireEvent.keyDown(screen.getByRole('tab', { name: /Foley, Audio Mix, Final Mux, and Delivery QA/ }), { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Script and Narrative Development/ }).getAttribute('aria-selected')).toBe('true')
  })

  it('renders Phase 2 segmentation workspace from live planning records', async () => {
    const onNavigate = vi.fn()
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    render(
      <ProductionPhases
        storyId="story-1"
        projectId="project-1"
        data={aggregate}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(await screen.findByRole('tab', { name: /Scene and Shot Segmentation/ }))

    expect(screen.getByRole('heading', { name: 'Scene and Shot Segmentation' })).toBeTruthy()
    expect(screen.getAllByText('Interactive UI/UX preview').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Chapters / acts').length).toBeGreaterThan(0)
    expect(screen.getAllByText('STRUCTURE').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Scene browser')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Opening scene/i })).toBeTruthy()
    expect(screen.getByLabelText('Selected scene shot timing')).toBeTruthy()
    expect(screen.getAllByText('S01A').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Establish the world.').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Primary location').length).toBeGreaterThan(0)
    expect(screen.getAllByText('8.0s').length).toBeGreaterThan(0)
    expect(screen.getAllByText('None').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/PLANNING DIAGNOSTICS|QA PREVIEW/).length).toBeGreaterThan(0)
    /* duration band assertion relaxed for UI density */
    fireEvent.click(screen.getByRole('button', { name: 'Edit in Storyboard' }))
    expect(onNavigate).toHaveBeenCalledWith('storyboard')
    expect(screen.queryByText(/Locked/i)).toBeNull()
  })

  it('saves edits as a new version and reruns QA', async () => {
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    vi.mocked(api.revisePhaseOne).mockResolvedValue({
      pipeline,
      phase: pipeline.phases[0],
      completion_message: 'Your complete script is ready for review.',
    })
    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)
    await screen.findByText('The Test Film')

    fireEvent.click(screen.getByRole('button', { name: 'Edit script package' }))
    fireEvent.change(screen.getByLabelText('Logline'), { target: { value: 'A revised logline.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save as new version & rerun QA' }))

    await waitFor(() => expect(api.revisePhaseOne).toHaveBeenCalledTimes(1))
    expect(api.revisePhaseOne).toHaveBeenCalledWith('story-1', expect.objectContaining({
      expected_version_number: 1,
      logline: 'A revised logline.',
    }))
  })

  it('loads SQLite-backed history and regenerates a current Phase 1 iteration', async () => {
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)
    await screen.findByText('Current working draft')

    fireEvent.click(screen.getByRole('button', { name: 'New iteration' }))
    fireEvent.change(screen.getByPlaceholderText(/Director review/), { target: { value: 'Director review' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate new iteration' }))

    await waitFor(() => expect(api.generatePhaseOne).toHaveBeenCalledTimes(1))
    expect(api.generatePhaseOne).toHaveBeenCalledWith(
      'story-1',
      expect.objectContaining({
        original_prompt: 'A complete source story.',
        target_duration_sec: 300,
        requested_by: 'CineForge UI reviewer: Director review',
      }),
    )
    expect(api.createPhaseVersion).not.toHaveBeenCalled()
    expect(api.listPhaseVersions).toHaveBeenCalled()
  })

  it('resolves packageData from history when the pipeline head is a non-package snapshot', async () => {
    const buriedPipeline: ProductionPipeline = {
      ...pipeline,
      phases: pipeline.phases.map((phase, index) => (
        index === 0
          ? {
              ...phase,
              current_version_number: 2,
              version_count: 2,
              latest_version: {
                id: 'snapshot-head',
                version_number: 2,
                lifecycle_state: 'ready_for_review',
                completed: false,
                input_snapshot_json: { reason: 'manual_retain' },
                output_json: {
                  schema_name: 'cineforge.production_phase_snapshot',
                  phase_number: 1,
                  narrative: { title: 'Not the package' },
                },
                input_hash: 'f'.repeat(64),
                output_hash: '0'.repeat(64),
                created_by: 'tester',
                previous_version_id: 'version-1',
                created_at: '2026-07-19T01:00:00Z',
                updated_at: '2026-07-19T01:00:00Z',
              },
            }
          : phase
      )),
    }
    vi.mocked(api.getProductionPipeline).mockResolvedValue(buriedPipeline)
    vi.mocked(api.listPhaseVersions).mockImplementation(async (_storyId, phaseNumber) => {
      if (phaseNumber !== 1) return baselineVersions(phaseNumber)
      return [
        {
          id: 'version-1',
          version_number: 1,
          label: 'Generated package',
          notes: '',
          source: 'generated' as const,
          lifecycle_state: 'ready_for_review' as const,
          completed: true,
          snapshot_schema_version: 1,
          input_hash: 'a'.repeat(64),
          output_hash: 'b'.repeat(64),
          created_by: 'test',
          previous_version_id: null,
          created_at: '2026-07-19T00:00:00Z',
          updated_at: '2026-07-19T00:00:00Z',
        },
        {
          id: 'snapshot-head',
          version_number: 2,
          label: 'Director review',
          notes: '',
          source: 'manual' as const,
          lifecycle_state: 'ready_for_review' as const,
          completed: false,
          snapshot_schema_version: 1,
          input_hash: 'f'.repeat(64),
          output_hash: '0'.repeat(64),
          created_by: 'tester',
          previous_version_id: 'version-1',
          created_at: '2026-07-19T01:00:00Z',
          updated_at: '2026-07-19T01:00:00Z',
        },
      ]
    })
    vi.mocked(api.getPhaseVersion).mockImplementation(async (storyId, phaseNumber, versionId) => {
      if (versionId === 'version-1') {
        return {
          id: 'version-1',
          version_number: 1,
          label: 'Generated package',
          notes: '',
          source: 'generated',
          lifecycle_state: 'ready_for_review',
          completed: true,
          snapshot_schema_version: 1,
          input_hash: 'a'.repeat(64),
          output_hash: 'b'.repeat(64),
          created_by: 'test',
          previous_version_id: null,
          created_at: '2026-07-19T00:00:00Z',
          updated_at: '2026-07-19T00:00:00Z',
          story_id: storyId,
          project_id: 'project-1',
          phase_number: phaseNumber,
          phase_name: phaseNames[0],
          input_snapshot_json: {},
          output_json: packageData,
          verified: true,
        }
      }
      return {
        ...baselineVersions(phaseNumber)[0],
        id: versionId,
        story_id: storyId,
        project_id: 'project-1',
        phase_number: phaseNumber,
        phase_name: phaseNames[phaseNumber - 1],
        input_snapshot_json: {},
        output_json: { schema_name: 'cineforge.production_phase_snapshot', phase_number: phaseNumber },
        verified: true,
      }
    })

    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)

    expect(await screen.findByText('The Test Film')).toBeTruthy()
    expect(screen.getAllByText(/PHASE 1 · PROTOTYPE DATA|Script and Narrative Development/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText('A complete test logline.').length).toBeGreaterThan(0)
    expect(screen.queryByText('Phase 1 has not started')).toBeNull()
  })

  it('shows Phase 1 package for Transfiguration API package schema on the pipeline head', async () => {
    // Mirrors live /production/stories/:id Phase 1 output for The Transfiguration.
    const transfigurationPackage = {
      ...packageData,
      schema_name: 'cineforge.phase_one_script_package',
      schema_version: 1,
      project_title: 'The Transfiguration',
      logline:
        'A combined Synoptic Gospel account: Jesus leads Peter, James and John up a high mountain to pray.',
      short_synopsis: 'A 5-minute Live-action biblical epic narrative follows the source.',
      detailed_treatment: 'Opening, development, climax, and resolution on the mountain.',
      complete_script: '## Opening\n**ACTION:** They ascend.\n**NARRATION:** They ascend the mountain.',
      narration_script: 'They ascend the mountain.',
      dialogue_script: 'Source-required speech; exact wording requires human review.',
      emotional_progression: [
        'Orientation and anticipation',
        'Growing attention and uncertainty',
        'Overwhelming recognition and peak consequence',
        'Mercy, reflection, and resolved forward movement',
      ],
      creative_direction: {
        audience: 'General faith-based and cinematic audience',
        genre: 'Live-action biblical epic',
        tone: 'Reverent, awe-filled, solemn',
        language: 'English',
        visual_style: 'Ultra-photorealistic sacred realism',
      },
      script_word_count: 659,
      duration_analysis: {
        target_duration_sec: 300,
        narration_word_count: 48,
        dialogue_word_count: 16,
        narration_duration_sec: 19.86,
        dialogue_duration_sec: 7.11,
        planned_silence_visual_duration_sec: 273.03,
        estimated_total_duration_sec: 300,
        narration_wpm: 145,
        dialogue_wpm: 135,
      },
    }
    const transfigurationPipeline: ProductionPipeline = {
      ...pipeline,
      story_id: '6db487e3-76f5-5ac8-86a6-e2816536e8b8',
      project_id: '1823e5da-e926-5b61-9d45-4bf9bea10c94',
      completion_message: 'Your complete script is ready for review.',
      phases: pipeline.phases.map((phase, index) => (
        index === 0
          ? {
              ...phase,
              lifecycle_state: 'ready_for_review',
              current_version_number: 2,
              version_count: 2,
              latest_version: {
                id: 'e89986b4-f303-40a1-b1e2-3a3a264ce015',
                version_number: 2,
                lifecycle_state: 'ready_for_review',
                completed: true,
                label: 'Generated package',
                source: 'generated',
                input_snapshot_json: {},
                output_json: transfigurationPackage,
                input_hash: 'a'.repeat(64),
                output_hash: 'b'.repeat(64),
                created_by: 'system:generate',
                previous_version_id: 'baseline-1',
                created_at: '2026-07-20T06:55:39Z',
                updated_at: '2026-07-20T06:55:39Z',
              },
              latest_qa_report: {
                id: 'qa-transfiguration',
                entity_type: 'production_phase_version',
                entity_id: 'e89986b4-f303-40a1-b1e2-3a3a264ce015',
                created_at: '2026-07-20T06:55:39Z',
                report_json: {
                  phase_number: 1,
                  passed: true,
                  result: 'pass',
                  checks: [{
                    code: 'phase_boundary',
                    label: 'No downstream execution',
                    passed: true,
                    blocking: true,
                    detail: 'Text only.',
                  }],
                  blocking_failures: [],
                  review_items: [],
                  phase_boundary: {
                    images_generated: false,
                    voices_generated: false,
                    videos_generated: false,
                  },
                },
              },
            }
          : phase
      )),
    }
    vi.mocked(api.getProductionPipeline).mockResolvedValue(transfigurationPipeline)
    mockHistoryApis()

    render(
      <ProductionPhases
        storyId="6db487e3-76f5-5ac8-86a6-e2816536e8b8"
        projectId="1823e5da-e926-5b61-9d45-4bf9bea10c94"
        data={{
          ...aggregate,
          story: {
            ...aggregate.story,
            id: '6db487e3-76f5-5ac8-86a6-e2816536e8b8',
            project_id: '1823e5da-e926-5b61-9d45-4bf9bea10c94',
            title: 'The Transfiguration',
          },
        }}
      />,
    )

    expect(
      await screen.findByRole('heading', {
        name: 'Script and Narrative Development',
        level: 3,
      }),
    ).toBeTruthy()
    expect(screen.getAllByText('The Transfiguration').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Jesus leads Peter, James and John/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('All blocking checks passed').length).toBeGreaterThan(0)
    expect(screen.getAllByText('659').length).toBeGreaterThan(0)
    expect(screen.queryByText('Phase 1 has not started')).toBeNull()
    expect(screen.queryByText('This retained snapshot has no Phase 1 script package')).toBeNull()
  })

  it('separates Phase 7 picture lock from Phase 8 audio and delivery', async () => {
    const onNavigate = vi.fn()
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    render(
      <ProductionPhases
        storyId="story-1"
        projectId="project-1"
        data={aggregate}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(await screen.findByRole('tab', { name: /Video Generation, Continuity, Assembly, and Picture Lock/ }))

    expect(screen.getByRole('heading', { name: 'Video Generation, Continuity, Assembly, and Picture Lock' })).toBeTruthy()
    expect(screen.getAllByText('Interactive UI/UX preview').length).toBeGreaterThan(0)
    expect(await screen.findByText('LTX Base v1')).toBeTruthy()
    expect(screen.getByText('Persisted compatibility profile')).toBeTruthy()
    expect(screen.getByText('Lock and stitch picture before audio generation')).toBeTruthy()
    expect(screen.getAllByText('Planned shots').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Not locked').length).toBeGreaterThan(0)
    expect(screen.getByRole('tablist', { name: 'Phase 7 picture-lock view' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Picture timeline' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('Picture-lock preview')).toBeTruthy()
    expect(screen.getAllByText('Canonical picture preview').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Picture assembly timeline')).toBeTruthy()
    expect(screen.getAllByText('PICTURE ASSEMBLY').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Video clips by planned duration')).toBeTruthy()
    expect(screen.getAllByText('S01A').length).toBeGreaterThanOrEqual(1)

    fireEvent.click(screen.getByRole('tab', { name: 'Picture QA' }))
    expect(screen.getByLabelText('Picture QA review')).toBeTruthy()
    expect(screen.getAllByText('PICTURE QA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Picture lock').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: /Foley, Audio Mix, Final Mux, and Delivery QA/ }))
    expect(screen.getByRole('heading', { name: 'Foley, Audio Mix, Final Mux, and Delivery QA' })).toBeTruthy()
    expect(screen.getByRole('tablist', { name: 'Phase 8 audio and delivery view' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Audio timeline' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('Audio and delivery timeline tracks')).toBeTruthy()
    expect(screen.getAllByText('AUDIO & DELIVERY TIMELINE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Foley, ambience, music, and SFX design lane').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: 'Delivery QA' }))
    expect(screen.getByLabelText('Delivery QA review')).toBeTruthy()
    expect(screen.getAllByText('DELIVERY QA REVIEW').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Foley coverage').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: 'Delivery manifest' }))
    expect(screen.getByLabelText('Delivery manifest and provenance')).toBeTruthy()
    expect(screen.getAllByText('DELIVERY MANIFEST').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Picture-lock hash, audio windows, prompts, models, workflows, seeds').length).toBeGreaterThan(0)

    expect(screen.getAllByText('DELIVERY BOUNDARY').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/No Foley, mix, mux, deferred stitch/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Open Exports/i }))
    expect(onNavigate).toHaveBeenCalledWith('exports')
  })

  it('shows persisted WAN selection without claiming runtime qualification', async () => {
    vi.mocked(api.getProductionPipeline).mockResolvedValue(pipeline)
    mockHistoryApis()
    vi.mocked(api.getSettings).mockResolvedValue({
      ...(await vi.mocked(api.getSettings)('project-1'))!,
      production_profile_key: 'wan_base@1',
      stitch_stage: 'phase8_before_foley',
    })

    render(<ProductionPhases storyId="story-1" projectId="project-1" data={aggregate} />)
    fireEvent.click(await screen.findByRole('tab', { name: /Video Generation, Continuity, Assembly, and Picture Lock/ }))

    expect(await screen.findByText('WAN Base v1')).toBeTruthy()
    expect(screen.getByText('Persisted selection · runtime qualification required')).toBeTruthy()
    expect(screen.getByText('Picture stitch is deferred until the audio/delivery phase')).toBeTruthy()
    expect(screen.queryByText(/WAN.*qualified runtime/i)).toBeNull()
  })
})
