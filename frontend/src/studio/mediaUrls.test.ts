import { describe, expect, it } from 'vitest'

import {
  artDirectionBoardUrl,
  characterPortraitUrl,
  isTransfigurationCanon,
  projectCoverUrl,
  startingFrameUrl,
} from './mediaUrls'

describe('mediaUrls dry-run honesty', () => {
  it('detects Transfiguration canon by name or known project id', () => {
    expect(isTransfigurationCanon({ projectName: 'The Transfiguration - Five-Minute' })).toBe(true)
    expect(isTransfigurationCanon({ projectId: '1823e5da-e926-5b61-9d45-4bf9bea10c94' })).toBe(true)
    expect(isTransfigurationCanon({ projectName: 'CineForge Verification Project' })).toBe(false)
  })

  it('prefers managed asset content over static codes', () => {
    expect(
      startingFrameUrl({
        title: 'S01A - Climb',
        assetId: 'asset-1',
        projectName: 'The Transfiguration',
      }),
    ).toMatch(/\/assets\/asset-1\/content$/)
  })

  it('does not bleed Transfiguration static frames onto other projects', () => {
    expect(
      startingFrameUrl({
        title: 'S01A - Climb',
        projectName: 'CineForge Verification Project',
      }),
    ).toBeNull()
    expect(
      projectCoverUrl({
        projectName: 'CineForge Verification Project',
        shotTitles: ['S01A - Climb'],
      }),
    ).toBeNull()
  })

  it('allows static canon only for Transfiguration when no managed asset', () => {
    expect(
      startingFrameUrl({
        title: 'S01A - Climb',
        projectName: 'The Transfiguration',
      }),
    ).toBe('/transfiguration/starting-images/S01A.webp')
    expect(
      projectCoverUrl({
        projectName: 'The Transfiguration',
        firstAssetId: null,
        shotTitles: [],
      }),
    ).toBe('/transfiguration/starting-images/S04B.webp')
    expect(
      artDirectionBoardUrl({
        sceneNumber: 1,
        projectName: 'The Transfiguration',
      }),
    ).toBe('/transfiguration/storyboards/scene-01.png?v=highres-numbered-1-through-8-v2')
  })

  it('uses managed asset for art boards and portraits when present', () => {
    expect(
      artDirectionBoardUrl({
        sceneNumber: 1,
        assetId: 'board-1',
        version: 'sha-1',
        projectName: 'Other',
      }),
    ).toMatch(/\/assets\/board-1\/content\?v=sha-1$/)
    expect(
      characterPortraitUrl({
        name: 'Jesus',
        assetId: 'char-1',
        projectName: 'Other',
      }),
    ).toMatch(/\/assets\/char-1\/content$/)
  })
})
