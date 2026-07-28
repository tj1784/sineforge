import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { ProductionPhase } from '../../api/client'
import type { SnapshotWorkspace } from '../snapshotWorkspace'
import { ProductionPhasePreview } from './ProductionPhasePreview'

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
})
