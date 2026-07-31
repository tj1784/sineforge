import { describe, expect, it } from 'vitest'
import {
  buildSequenceSheetRequest,
  createSequenceRow,
  parseSequenceSheetImport,
  validateSequenceRows,
} from './sequenceSheet'

describe('Sequence Sheet import and validation', () => {
  it('parses quoted CSV into the canonical LTX-only row contract', () => {
    const rows = parseSequenceSheetImport(
      [
        'output_name,prompt,duration_sec,seed,input_asset_id,character_ids',
        'Opening,"The driver enters the car, then closes the door.",10,derive,start-asset-1,char-1|char-2',
        'Drive,"The car pulls away.",12,42,,char-1',
      ].join('\n'),
      'sequence.csv',
    )

    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      order: 1,
      template_key: 'ltx-i2v',
      model_profile: 'ltx_base@2',
      mode: 'i2v',
      duration_sec: 10,
      seed: 'derive',
      input_asset_id: 'start-asset-1',
      continuity_source: 'asset:start-asset-1',
      character_ids: ['char-1', 'char-2'],
    })
    expect(rows[1]).toMatchObject({
      order: 2,
      duration_sec: 12,
      seed: 42,
      continuity_source: 'previous_last_frame',
    })
    expect(validateSequenceRows(rows)).toEqual([])
  })

  it('rejects WAN imports instead of silently changing their model family', () => {
    expect(() =>
      parseSequenceSheetImport(
        JSON.stringify({
          schema_version: 'sineforge.sequence-sheet/v1',
          project_id: 'project-1',
          model_family: 'wan',
          rows: [{ prompt: 'A WAN row.' }],
        }),
        'wan.json',
      ),
    ).toThrow(/WAN is on hold/i)
  })

  it('blocks missing first-frame input and durations outside 8–15 seconds', () => {
    const rows = [
      createSequenceRow(1, {
        prompt: 'The subject walks toward the car.',
        duration_sec: 7,
      }),
    ]
    const issues = validateSequenceRows(rows)

    expect(issues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining(['duration_out_of_range', 'first_row_input_required']),
    )
  })

  it('serializes project scope and the versioned LTX schema', () => {
    const rows = [
      createSequenceRow(1, {
        prompt: 'The subject enters the car.',
        input_asset_id: 'asset-1',
        continuity_source: 'asset:asset-1',
      }),
    ]

    expect(buildSequenceSheetRequest('project-12345678', rows)).toMatchObject({
      schema_version: 'sineforge.sequence-sheet/v1',
      project_id: 'project-12345678',
      model_family: 'ltx',
      rows: [
        {
          order: 1,
          mode: 'i2v',
          input_asset_id: 'asset-1',
          continuity_source: 'asset:asset-1',
        },
      ],
    })
  })
})
