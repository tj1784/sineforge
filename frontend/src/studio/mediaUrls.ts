import { planningAssetContentUrl } from '../api/client'

/** Shot codes used by the published Gold Sites media pack (S01A.webp, …). */
const SHOT_CODE_RE = /\b(S\d{2}[A-Z])\b/i

/**
 * Static webp pack under /public/transfiguration is Transfiguration-only canon.
 * Never use it for unrelated projects or as a substitute for assigned managed assets.
 */
export function isTransfigurationCanon(input: {
  projectId?: string | null
  projectName?: string | null
  storyTitle?: string | null
}): boolean {
  const text = `${input.projectName ?? ''} ${input.storyTitle ?? ''}`.toLowerCase()
  if (text.includes('transfiguration')) return true
  // Known bundled local Transfiguration project id (stable across restarts of this DB).
  if (input.projectId === '1823e5da-e926-5b61-9d45-4bf9bea10c94') return true
  return false
}

export function shotCodeFromLabel(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(SHOT_CODE_RE)
  return match ? match[1].toUpperCase() : null
}

/** Published Sites path: /transfiguration/starting-images/S04B.webp */
export function staticStartingImageUrl(code: string): string {
  return `/transfiguration/starting-images/${code.toUpperCase()}.webp`
}

export function staticCharacterImageUrl(slug: string): string {
  return `/transfiguration/characters/${slug.toLowerCase()}.webp`
}

const TRANSFIGURATION_STORYBOARD_VERSION = 'highres-numbered-1-through-8-v2'

export function staticStoryboardUrl(sceneNumber: number): string {
  return `/transfiguration/storyboards/scene-${String(sceneNumber).padStart(2, '0')}.png?v=${TRANSFIGURATION_STORYBOARD_VERSION}`
}

export function artDirectionBoardUrl(input: {
  sceneNumber?: number | null
  filename?: string | null
  assetId?: string | null
  version?: string | null
  projectId?: string | null
  projectName?: string | null
  storyTitle?: string | null
}): string | null {
  // Managed asset bytes always win when present.
  if (input.assetId) return planningAssetContentUrl(input.assetId, input.version)

  if (!isTransfigurationCanon(input)) return null
  if (typeof input.sceneNumber === 'number' && input.sceneNumber > 0) {
    return staticStoryboardUrl(input.sceneNumber)
  }
  return null
}

/**
 * Resolve a starting-frame display URL.
 * 1) Assigned managed asset content (always preferred — dry-run honesty)
 * 2) Transfiguration static pack only when no asset and project is Transfiguration canon
 */
export function startingFrameUrl(input: {
  title?: string | null
  code?: string | null
  filename?: string | null
  assetId?: string | null
  version?: string | null
  projectId?: string | null
  projectName?: string | null
  storyTitle?: string | null
}): string | null {
  if (input.assetId) return planningAssetContentUrl(input.assetId, input.version)

  if (!isTransfigurationCanon(input)) return null

  const code =
    shotCodeFromLabel(input.code) ||
    shotCodeFromLabel(input.title) ||
    shotCodeFromLabel(input.filename)
  if (code) return staticStartingImageUrl(code)
  return null
}

export function projectCoverUrl(input: {
  projectId?: string | null
  projectName?: string | null
  storyTitle?: string | null
  shotTitles?: Array<string | null | undefined>
  firstAssetId?: string | null
  firstAssetVersion?: string | null
}): string | null {
  // Prefer a real managed starting-image assignment on any project.
  if (input.firstAssetId) return planningAssetContentUrl(input.firstAssetId, input.firstAssetVersion)

  if (!isTransfigurationCanon(input)) return null

  for (const title of input.shotTitles ?? []) {
    const code = shotCodeFromLabel(title)
    if (code) return staticStartingImageUrl(code)
  }
  // Published Transfiguration cover is exactly S04B.webp
  return staticStartingImageUrl('S04B')
}

const CHARACTER_SLUGS: Record<string, string> = {
  jesus: 'jesus',
  peter: 'peter',
  james: 'james',
  john: 'john',
  moses: 'moses',
  elijah: 'elijah',
}

export function characterPortraitUrl(input: {
  name?: string | null
  assetId?: string | null
  version?: string | null
  projectId?: string | null
  projectName?: string | null
  storyTitle?: string | null
}): string | null {
  if (input.assetId) return planningAssetContentUrl(input.assetId, input.version)

  if (!isTransfigurationCanon(input)) return null

  const name = (input.name ?? '').toLowerCase()
  for (const [key, slug] of Object.entries(CHARACTER_SLUGS)) {
    if (name.includes(key)) return staticCharacterImageUrl(slug)
  }
  return null
}
