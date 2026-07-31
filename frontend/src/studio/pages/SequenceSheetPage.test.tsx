import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../api/client'
import { useStudio } from '../StudioState'
import { SequenceSheetPage } from './SequenceSheetPage'

vi.mock('../StudioState', () => ({
  useStudio: vi.fn(),
}))

const projectId = 'project-12345678'

beforeEach(() => {
  window.localStorage.clear()
  vi.mocked(useStudio).mockReturnValue({
    projectId,
    data: {
      story: {
        id: 'story-1',
        project_id: projectId,
        title: 'Sequence Test',
      },
      chapters: [],
    },
  } as never)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('SequenceSheetPage', () => {
  it('keeps WAN unavailable and sends canonical project-scoped dry-run and execute payloads', async () => {
    const dryRun = vi.spyOn(api, 'dryRunSequenceSheet').mockResolvedValue({
      ok: true,
      valid: true,
      status: 'ready',
      ready_to_execute: true,
      qualification: { qualified: true, blockers: [] },
      validation: { valid: true, issues: [] },
    })
    const execute = vi.spyOn(api, 'executeSequenceSheet').mockResolvedValue({
      ok: true,
      status: 'queued',
      job_id: 'job-1',
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<SequenceSheetPage />)

    expect(screen.getByText('WAN on hold')).toBeTruthy()
    expect(screen.getByText(/Native LTX audio stays synchronized/i)).toBeTruthy()
    expect(screen.getByText(/WAN Phase 8 is not used/i)).toBeTruthy()
    expect(screen.queryByRole('option', { name: /WAN/i })).toBeNull()

    fireEvent.change(screen.getByLabelText('LTX video prompt'), {
      target: { value: 'The worker leaves the office and walks toward the parked car.' },
    })
    fireEvent.change(screen.getByLabelText('Input asset ID'), {
      target: { value: 'starting-image-1' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Dry run' }))

    await waitFor(() => expect(dryRun).toHaveBeenCalledTimes(1))
    expect(dryRun.mock.calls[0][0]).toBe(projectId)
    expect(dryRun.mock.calls[0][1]).toMatchObject({
      schema_version: 'sineforge.sequence-sheet/v1',
      project_id: projectId,
      model_family: 'ltx',
      rows: [
        {
          template_key: 'ltx-i2v',
          model_profile: 'ltx_base@2',
          mode: 'i2v',
          duration_sec: 10,
          seed: 'derive',
          input_asset_id: 'starting-image-1',
          continuity_source: 'asset:starting-image-1',
        },
      ],
    })

    const executeButton = await screen.findByRole('button', { name: 'Execute LTX sequence' })
    await waitFor(() => expect((executeButton as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(executeButton)

    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1))
    expect(execute.mock.calls[0][0]).toBe(projectId)
    expect(execute.mock.calls[0][1]).toMatchObject({
      ...dryRun.mock.calls[0][1],
      allow_rendering: true,
    })
    expect(execute.mock.calls[0][1].idempotency_key).toMatch(/^sequence-/)
    expect(await screen.findByText(/Execution response · queued/i)).toBeTruthy()
  })

  it('imports canonical JSON text and rejects a WAN sheet in the visible validation area', () => {
    render(<SequenceSheetPage />)
    fireEvent.click(screen.getByText('Paste CSV or JSON'))
    fireEvent.change(screen.getByLabelText('Import content'), {
      target: {
        value: JSON.stringify({
          model_family: 'wan',
          rows: [{ prompt: 'A WAN row.' }],
        }),
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Replace rows from text' }))

    expect(screen.getByRole('alert').textContent).toMatch(/WAN is on hold/i)
  })
})
