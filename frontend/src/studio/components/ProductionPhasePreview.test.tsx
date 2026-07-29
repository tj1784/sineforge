import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, type ProductionPhase } from '../../api/client'
import type { SnapshotWorkspace } from '../snapshotWorkspace'
import { ProductionPhasePreview } from './ProductionPhasePreview'

vi.mock('../../api/client', () => ({
  api: {
    queuePhaseSevenVideos: vi.fn(),
  },
}))

afterEach(() => cleanup())

function phase(phaseNumber: 7 | 8): ProductionPhase {
  return {
    id: `phase-${phaseNumber}`,
    phase_number: phaseNumber,
    name: phaseNumber === 7
      ? 'Video Generation, Continuity, Assembly, and Picture Lock'
      : 'Foley, Audio Mix, Final Mux, and Delivery QA',
    lifecycle_state: 'not_started',
    current_version_number: 1,
    version_count: 1,
    is_locked: false,
    locked_reason: null,
    is_stale: false,
    stale_reason: null,
    generation_completed_at: null,
    approved_at: null,
    latest_version: null,
    latest_qa_report: null,
  }
}

function workspace(phaseNumber: 7 | 8): SnapshotWorkspace {
  const picture = {
    production_profile_key: 'wan_base@1',
    stitch_stage: 'phase8_before_foley',
    picture_locked: false,
    qa_state: 'not_evaluated',
  }
  const audioDelivery = phaseNumber === 8
    ? { planned_runtime_sec: 0, qa_state: 'not_evaluated' }
    : null
  return {
    phaseNumber,
    storyId: 'story-1',
    projectId: 'project-1',
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
    picture,
    audioDelivery,
    assembly: phaseNumber === 7 ? picture : audioDelivery,
    targetDurationSec: 0,
    completeness: {
      complete: true,
      phaseNumber,
      missingDomains: [],
      schemaVersion: 2,
      reason: null,
    },
  }
}

describe('ProductionPhasePreview historical settings isolation', () => {
  it.each([7, 8] as const)(
    'uses retained Phase %s profile and stitch settings instead of current project settings',
    (phaseNumber) => {
      render(
        <ProductionPhasePreview
          phase={phase(phaseNumber)}
          workspace={workspace(phaseNumber)}
          historical
          productionProfileKey="ltx_base@1"
          stitchStage="phase7_before_audio"
        />,
      )

      expect(screen.getByText('WAN Base v1')).toBeTruthy()
      expect(screen.getByText('Picture stitch is deferred until the audio/delivery phase')).toBeTruthy()
      expect(screen.queryByText('LTX Base v1')).toBeNull()
    },
  )

  it('queues all Phase 7 video prompts when approved starting images are present', async () => {
    vi.mocked(api.queuePhaseSevenVideos).mockResolvedValue({
      queued_count: 1,
      blocked_count: 0,
      required_count: 1,
      message: 'Queued 1 Phase 7 video prompt in ComfyAPI Runner.',
      runner_url: 'http://127.0.0.1:8022',
      workflow_label: 'CineForge Phase 7 WAN 2.1 LightX2V I2V 480p',
      jobs: [{
        shot_id: 'shot-1',
        starting_image_asset_id: 'asset-start-1',
        runner_job_id: 'runner-job-1',
        shot_code: 'S01A',
        prompt: 'Video prompt',
        negative_prompt: 'Negative prompt',
        seed: 123,
        frame_count: 121,
        input_image: 'cineforge\\project-1\\phase7\\s01a.png',
        output_prefix: 'cineforge\\project-1\\phase7\\s01a_video',
      }],
      blockers: [],
    })
    const readyWorkspace: SnapshotWorkspace = {
      ...workspace(7),
      targetDurationSec: 8,
      scenes: [{
        id: 'scene-1',
        chapter_id: 'chapter-1',
        title: 'Opening scene',
        location: 'Primary location',
      }],
      shots: [{
        id: 'shot-1',
        scene_id: 'scene-1',
        title: 'Opening image',
        duration_sec: 8,
        visual_description: 'A grounded opening frame.',
        starting_image_required: true,
        starting_image_asset_id: 'asset-start-1',
        video_prompt: 'A slow controlled push in.',
      }],
      planningMedia: [{
        id: 'asset-start-1',
        kind: 'starting_image',
        managed_uri: 'cineforge-planning://project-1/starting_image/frame.png',
        content_hash: 'a'.repeat(64),
        original_filename: 'frame.png',
        width: 1024,
        height: 576,
        approval_state: 'approved',
      }],
    }

    render(
      <ProductionPhasePreview
        phase={phase(7)}
        workspace={readyWorkspace}
        historical={false}
        productionProfileKey="wan_base@1"
        stitchStage="phase7_before_audio"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Generate video' }))

    await waitFor(() => expect(api.queuePhaseSevenVideos).toHaveBeenCalledWith(
      'story-1',
      expect.objectContaining({
        requested_by: 'CineForge Phase 7 video handoff',
      }),
    ))
    expect(await screen.findByText(/Open ComfyAPI Runner to watch 1 job/i)).toBeTruthy()
  })
})
