export type ChapterIntakeDraft = {
  title: string
  summary: string
  sourcePrompt: string
  targetDurationSec: number
  narrativePurpose: string
  dramaticProgression: string
  productionNotes: string
}

export function makeChapterIntakeDraft(index: number, targetDurationSec = 60): ChapterIntakeDraft {
  return {
    title: `Chapter ${index + 1}`,
    summary: '',
    sourcePrompt: '',
    targetDurationSec: Math.max(6, Math.round(targetDurationSec)),
    narrativePurpose: '',
    dramaticProgression: '',
    productionNotes: '',
  }
}

export function chapterDurationParts(totalSeconds: number) {
  const clamped = Math.max(6, Math.round(Number.isFinite(totalSeconds) ? totalSeconds : 60))
  return {
    minutes: Math.floor(clamped / 60),
    seconds: clamped % 60,
  }
}

export function coerceChapterDuration(minutes: number, seconds: number) {
  return Math.max(6, Math.min(21_600, Math.max(0, minutes) * 60 + Math.max(0, Math.min(59, seconds))))
}
