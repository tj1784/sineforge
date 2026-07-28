import {
  chapterDurationParts,
  coerceChapterDuration,
  type ChapterIntakeDraft,
} from './chapterIntake'

type ChapterIntakeFormProps = {
  draft: ChapterIntakeDraft
  index: number
  disabled?: boolean
  onChange: <Key extends keyof ChapterIntakeDraft>(key: Key, value: ChapterIntakeDraft[Key]) => void
}

export function ChapterIntakeForm({ draft, index, disabled = false, onChange }: ChapterIntakeFormProps) {
  const duration = chapterDurationParts(draft.targetDurationSec)
  const code = `CH${String(index + 1).padStart(2, '0')}`

  return (
    <div className="chapter-intake-form">
      <section className="chapter-intake-step">
        <header><span>1</span><b>{code} foundation</b></header>
        <div className="wizard-form">
          <label>
            Chapter title
            <input
              aria-label={`${code} title`}
              disabled={disabled}
              value={draft.title}
              onChange={(event) => onChange('title', event.target.value)}
              placeholder={`Chapter ${index + 1}`}
            />
          </label>
          <label>
            Chapter summary
            <textarea
              aria-label={`${code} summary`}
              disabled={disabled}
              value={draft.summary}
              onChange={(event) => onChange('summary', event.target.value)}
              placeholder="What happens in this chapter?"
            />
          </label>
        </div>
      </section>

      <section className="chapter-intake-step">
        <header><span>2</span><b>Story &amp; timing</b></header>
        <div className="wizard-form">
          <label>
            Chapter source prompt
            <textarea
              aria-label={`${code} source prompt`}
              disabled={disabled}
              value={draft.sourcePrompt}
              onChange={(event) => onChange('sourcePrompt', event.target.value)}
              placeholder="Required beats, source material, references, or emotional turns for this chapter."
            />
          </label>
        </div>
        <div className="runtime-fields chapter-runtime-fields">
          <label>
            Minutes
            <input
              aria-label={`${code} target minutes`}
              disabled={disabled}
              type="number"
              min="0"
              max="360"
              value={duration.minutes}
              onChange={(event) => onChange('targetDurationSec', coerceChapterDuration(Number(event.target.value), duration.seconds))}
            />
          </label>
          <label>
            Seconds
            <input
              aria-label={`${code} target seconds`}
              disabled={disabled}
              type="number"
              min="0"
              max="59"
              value={duration.seconds}
              onChange={(event) => onChange('targetDurationSec', coerceChapterDuration(duration.minutes, Number(event.target.value)))}
            />
          </label>
          <div>
            <span>Chapter target</span>
            <b>{duration.minutes}:{String(duration.seconds).padStart(2, '0')}</b>
            <small>Used as planning guidance.</small>
          </div>
        </div>
      </section>

      <section className="chapter-intake-step">
        <header><span>3</span><b>Production defaults</b></header>
        <div className="wizard-form">
          <label>
            Narrative purpose
            <textarea
              aria-label={`${code} narrative purpose`}
              disabled={disabled}
              value={draft.narrativePurpose}
              onChange={(event) => onChange('narrativePurpose', event.target.value)}
              placeholder="Why this chapter exists in the story."
            />
          </label>
          <label>
            Dramatic progression
            <textarea
              aria-label={`${code} dramatic progression`}
              disabled={disabled}
              value={draft.dramaticProgression}
              onChange={(event) => onChange('dramaticProgression', event.target.value)}
              placeholder="What changes from the start to the end?"
            />
          </label>
          <label>
            Production notes
            <textarea
              aria-label={`${code} production notes`}
              disabled={disabled}
              value={draft.productionNotes}
              onChange={(event) => onChange('productionNotes', event.target.value)}
              placeholder="Continuity, reference, visual, or adaptation notes for this chapter."
            />
          </label>
        </div>
      </section>
    </div>
  )
}
