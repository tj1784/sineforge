import { describe, expect, it } from 'vitest'

import type { PhaseVersionDetail, StoryboardAggregate } from '../api/client'
import {
  assessSnapshotCompleteness,
  snapshotMetricsFromWorkspace,
  validateHistoricalDetail,
  workspaceFromAggregate,
  workspaceFromHistoricalDetail,
} from './snapshotWorkspace'

const baseDetail = (overrides: Partial<PhaseVersionDetail> = {}): PhaseVersionDetail => ({
  id: 'version-1',
  version_number: 1,
  label: 'Baseline',
  notes: '',
  source: 'baseline',
  snapshot_schema_version: 1,
  lifecycle_state: 'not_started',
  completed: false,
  input_snapshot_json: {},
  output_json: {
    schema_name: 'cineforge.production_phase_snapshot',
    snapshot_schema_version: 1,
    phase_number: 2,
    story_id: 'story-1',
    project_id: 'project-1',
    structure: {
      chapters: [{ id: 'c1', title: 'Act I', order_index: 0 }],
      scenes: [{ id: 'sc1', chapter_id: 'c1', title: 'Ridge', order_index: 0 }],
      shots: [{
        id: 'sh1',
        scene_id: 'sc1',
        title: 'Wide',
        duration_sec: 8,
        location: 'Ridge',
        order_index: 0,
        continuity_source_type: 'none',
      }],
    },
  },
  input_hash: 'a'.repeat(64),
  output_hash: 'b'.repeat(64),
  created_by: 'system',
  previous_version_id: null,
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
  story_id: 'story-1',
  project_id: 'project-1',
  phase_number: 2,
  phase_name: 'Scene and Shot Segmentation',
  verified: true,
  ...overrides,
})

describe('snapshotWorkspace historical isolation', () => {
  it('builds phase 2 workspace only from verified snapshot structure', () => {
    const { workspace, error } = workspaceFromHistoricalDetail(baseDetail(), {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 2,
    })
    expect(error).toBeNull()
    expect(workspace?.completeness.complete).toBe(true)
    expect(workspace?.chapters).toHaveLength(1)
    expect(workspace?.scenes[0]?.title).toBe('Ridge')
    expect(workspace?.shots[0]?.title).toBe('Wide')
  })

  it('rejects cross-project and cross-phase details without substituting data', () => {
    expect(
      validateHistoricalDetail(baseDetail(), {
        storyId: 'story-1',
        projectId: 'other-project',
        phaseNumber: 2,
      }),
    ).toMatch(/different project/i)

    expect(
      validateHistoricalDetail(baseDetail(), {
        storyId: 'story-1',
        projectId: 'project-1',
        phaseNumber: 3,
      }),
    ).toMatch(/different production phase/i)

    const { workspace, error } = workspaceFromHistoricalDetail(baseDetail(), {
      storyId: 'story-1',
      projectId: 'other-project',
      phaseNumber: 2,
    })
    expect(workspace).toBeNull()
    expect(error).toMatch(/different project/i)
  })

  it('marks incomplete legacy snapshots without inventing domains', () => {
    const incomplete = baseDetail({
      phase_number: 3,
      output_json: {
        schema_name: 'cineforge.production_phase_snapshot',
        snapshot_schema_version: 1,
        phase_number: 3,
        story_id: 'story-1',
        project_id: 'project-1',
        // missing identity domain
      },
    })
    const completeness = assessSnapshotCompleteness(
      incomplete.output_json as Record<string, unknown>,
      3,
    )
    expect(completeness.complete).toBe(false)
    expect(completeness.missingDomains).toContain('identity')

    const { workspace, error } = workspaceFromHistoricalDetail(incomplete, {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 3,
    })
    expect(error).toBeNull()
    expect(workspace?.completeness.complete).toBe(false)
    expect(workspace?.characters).toEqual([])
  })

  it('keeps legacy Phase 7 assembly snapshots readable', () => {
    const detail = baseDetail({
      snapshot_schema_version: 1,
      phase_number: 7,
      phase_name: 'Video Generation, Assembly, and Final QA',
      output_json: {
        schema_name: 'cineforge.production_phase_snapshot',
        snapshot_schema_version: 1,
        phase_number: 7,
        story_id: 'story-1',
        project_id: 'project-1',
        assembly: {
          planned_runtime_sec: 30,
          qa_state: 'not_evaluated',
        },
      },
    })

    const result = workspaceFromHistoricalDetail(detail, {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 7,
    })

    expect(result.error).toBeNull()
    expect(result.workspace?.completeness.complete).toBe(true)
    expect(result.workspace?.picture?.planned_runtime_sec).toBe(30)
    expect(result.workspace?.assembly?.planned_runtime_sec).toBe(30)
  })

  it('maps schema v2 picture and audio-delivery domains without conflating them', () => {
    const phaseSeven = baseDetail({
      snapshot_schema_version: 2,
      phase_number: 7,
      phase_name: 'Video Generation, Continuity, Assembly, and Picture Lock',
      output_json: {
        schema_name: 'cineforge.production_phase_snapshot',
        snapshot_schema_version: 2,
        phase_number: 7,
        story_id: 'story-1',
        project_id: 'project-1',
        picture: { picture_locked: true, qa_state: 'passed' },
      },
    })
    const phaseEight = baseDetail({
      snapshot_schema_version: 2,
      phase_number: 8,
      phase_name: 'Foley, Audio Mix, Final Mux, and Delivery QA',
      output_json: {
        schema_name: 'cineforge.production_phase_snapshot',
        snapshot_schema_version: 2,
        phase_number: 8,
        story_id: 'story-1',
        project_id: 'project-1',
        audio_delivery: { delivery_ready: true, qa_state: 'passed' },
      },
    })

    const picture = workspaceFromHistoricalDetail(phaseSeven, {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 7,
    }).workspace
    const audio = workspaceFromHistoricalDetail(phaseEight, {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 8,
    }).workspace

    expect(picture?.picture?.picture_locked).toBe(true)
    expect(picture?.audioDelivery).toBeNull()
    expect(audio?.audioDelivery?.delivery_ready).toBe(true)
    expect(audio?.picture).toBeNull()
  })

  it('keeps current-draft aggregate metrics independent from historical workspace', () => {
    const aggregate = {
      revision: 'r1',
      content_hash: 'h1',
      planned_duration_sec: 8,
      discrepancy_sec: 0,
      story: {
        id: 'story-1',
        project_id: 'project-1',
        title: 'Current Draft Title',
        base_story: 'Current draft story',
        target_duration_sec: 120,
      },
      chapters: [{
        id: 'c1',
        order_index: 0,
        title: 'Current chapter',
        summary: null,
        duration_sec: 8,
        scenes: [{
          id: 'sc1',
          order_index: 0,
          title: 'Current scene',
          summary: null,
          duration_sec: 8,
          shots: [{
            id: 'sh1',
            order_index: 0,
            title: 'Current shot',
            duration_sec: 8,
            location: 'Current location',
            continuity_source_type: 'none',
            starting_image_required: false,
            approval_state: 'draft',
            production_status: 'planned',
          }],
        }],
      }],
      characters: [{
        id: 'ch1',
        name: 'Current Character',
        role: 'Lead',
        approval_state: 'draft',
      }],
      voices: [],
    } as unknown as StoryboardAggregate

    const current = workspaceFromAggregate(aggregate, 2)
    const historical = workspaceFromHistoricalDetail(baseDetail(), {
      storyId: 'story-1',
      projectId: 'project-1',
      phaseNumber: 2,
    }).workspace

    expect(current.shots[0]?.title).toBe('Current shot')
    expect(historical?.shots[0]?.title).toBe('Wide')
    expect(snapshotMetricsFromWorkspace(current)[2].value).toBe(1)
    expect(snapshotMetricsFromWorkspace(historical)[0].value).toBe(1)
  })
})
