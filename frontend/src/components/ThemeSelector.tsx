import {
  CREATIVE_THEMES,
  type BiblicalContextDraft,
  type CreativeThemeId,
} from '../themes'

type ThemeSelectorProps = {
  value: CreativeThemeId
  context: BiblicalContextDraft
  disabled?: boolean
  name?: string
  onChange: (themeId: CreativeThemeId) => void
  onContextChange: <Key extends keyof BiblicalContextDraft>(
    key: Key,
    value: BiblicalContextDraft[Key],
  ) => void
}

const historicalPresets = [
  ['hb_patriarchal_canaan', 'Hebrew Bible · Patriarchal Canaan'],
  ['hb_exodus_egypt_sinai', 'Hebrew Bible · Egypt and Sinai'],
  ['hb_iron_age_israel_judah', 'Hebrew Bible · Iron Age Israel/Judah'],
  ['hb_assyrian_babylonian_exile', 'Hebrew Bible · Assyrian/Babylonian exile'],
  ['hb_persian_return', 'Hebrew Bible · Persian return'],
  ['nt_herodian_galilee_judea', 'New Testament · Herodian Galilee/Judea'],
  ['nt_jerusalem_second_temple', 'New Testament · Jerusalem/Second Temple'],
  ['nt_roman_military_admin', 'New Testament · Roman administration/military'],
  ['nt_acts_eastern_mediterranean', 'New Testament · Acts/eastern Mediterranean'],
  ['biblical_visionary', 'Biblical · passage-specific vision'],
] as const

export function ThemeSelector({
  value,
  context,
  disabled = false,
  name = 'creative-theme',
  onChange,
  onContextChange,
}: ThemeSelectorProps) {
  return (
    <fieldset className="theme-fieldset" disabled={disabled}>
      <legend>Creative theme <em>Generated content</em></legend>
      <div className="theme-options">
        {CREATIVE_THEMES.map((theme) => (
          <label className="theme-card" key={theme.id}>
            <input
              type="radio"
              name={name}
              value={theme.id}
              checked={value === theme.id}
              onChange={() => onChange(theme.id)}
            />
            <span><b>{theme.label}</b><small>{theme.description}</small></span>
          </label>
        ))}
      </div>

      {value === 'biblical' ? (
        <section className="biblical-context" aria-labelledby={`${name}-biblical-context`}>
          <header>
            <div>
              <span>BIBLICAL CONTEXT</span>
              <h3 id={`${name}-biblical-context`}>Anchor the source and historical world</h3>
            </div>
            <small>Required for generation</small>
          </header>
          <p>These fields prevent one generic “biblical” look from being applied across different centuries and regions.</p>
          <div className="biblical-context-grid">
            <label>
              Canon context
              <select
                aria-label="Biblical canon context"
                required
                value={context.canon_context}
                onChange={(event) => onContextChange('canon_context', event.target.value as BiblicalContextDraft['canon_context'])}
              >
                <option value="">Select canon…</option>
                <option value="hebrew_bible">Hebrew Bible</option>
                <option value="new_testament">New Testament</option>
              </select>
            </label>
            <label>
              Scripture reference <em>Optional</em>
              <input value={context.scripture_reference} onChange={(event) => onContextChange('scripture_reference', event.target.value)} placeholder="e.g. Luke 15:11–32" />
            </label>
            <label>
              Narrative period
              <input required value={context.narrative_period} onChange={(event) => onContextChange('narrative_period', event.target.value)} placeholder="e.g. Early first century CE" />
            </label>
            <label>
              Historical preset
              <select
                aria-label="Biblical historical preset"
                required
                value={context.historical_preset}
                onChange={(event) => onContextChange('historical_preset', event.target.value as BiblicalContextDraft['historical_preset'])}
              >
                <option value="">Select historical setting…</option>
                {historicalPresets.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label>
              Region
              <input required value={context.region} onChange={(event) => onContextChange('region', event.target.value)} placeholder="e.g. rural Galilee" />
            </label>
            <label>
              Cultures
              <input required value={context.culture} onChange={(event) => onContextChange('culture', event.target.value)} placeholder="Comma-separated, e.g. Galilean Jewish" />
            </label>
            <label>
              Roman presence
              <select required value={context.roman_presence} onChange={(event) => onContextChange('roman_presence', event.target.value as BiblicalContextDraft['roman_presence'])}>
                <option value="">Select presence…</option>
                <option value="none">None</option>
                <option value="ambient_rule">Ambient rule</option>
                <option value="civic_administration">Civic administration</option>
                <option value="military">Military</option>
                <option value="imperial_center">Imperial center</option>
              </select>
            </label>
            <label>
              Sacred representation
              <select required value={context.sacred_representation_policy} onChange={(event) => onContextChange('sacred_representation_policy', event.target.value as BiblicalContextDraft['sacred_representation_policy'])}>
                <option value="">Select policy…</option>
                <option value="indirect_manifestation">Indirect manifestation</option>
                <option value="text_explicit">Text-explicit only</option>
                <option value="traditional_iconography">Traditional iconography</option>
              </select>
            </label>
            <label>
              Angel depiction
              <select required value={context.angel_policy} onChange={(event) => onContextChange('angel_policy', event.target.value as BiblicalContextDraft['angel_policy'])}>
                <option value="">Select policy…</option>
                <option value="human_messenger_default">Human messenger by default</option>
                <option value="text_specific_being">Text-specific being</option>
                <option value="traditional_winged">Traditional winged</option>
              </select>
            </label>
            <label>
              Miracle intensity
              <select required value={context.miracle_intensity} onChange={(event) => onContextChange('miracle_intensity', event.target.value as BiblicalContextDraft['miracle_intensity'])}>
                <option value="">Select intensity…</option>
                <option value="restrained">Restrained</option>
                <option value="cinematic">Cinematic</option>
                <option value="visionary">Visionary</option>
              </select>
            </label>
          </div>
        </section>
      ) : null}
    </fieldset>
  )
}
