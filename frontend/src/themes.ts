export type CreativeThemeId = 'default' | 'greek_mythology' | 'biblical'

export type BiblicalContext = {
  canon_context: 'hebrew_bible' | 'new_testament'
  scripture_reference?: string | null
  narrative_period: string
  historical_preset:
    | 'hb_patriarchal_canaan'
    | 'hb_exodus_egypt_sinai'
    | 'hb_iron_age_israel_judah'
    | 'hb_assyrian_babylonian_exile'
    | 'hb_persian_return'
    | 'nt_herodian_galilee_judea'
    | 'nt_jerusalem_second_temple'
    | 'nt_roman_military_admin'
    | 'nt_acts_eastern_mediterranean'
    | 'biblical_visionary'
  region: string
  culture: string[]
  roman_presence: 'none' | 'ambient_rule' | 'civic_administration' | 'military' | 'imperial_center'
  sacred_representation_policy: 'indirect_manifestation' | 'text_explicit' | 'traditional_iconography'
  angel_policy: 'human_messenger_default' | 'text_specific_being' | 'traditional_winged'
  miracle_intensity: 'restrained' | 'cinematic' | 'visionary'
}

export type BiblicalContextDraft = {
  canon_context: '' | BiblicalContext['canon_context']
  scripture_reference: string
  narrative_period: string
  historical_preset: '' | BiblicalContext['historical_preset']
  region: string
  culture: string
  roman_presence: '' | BiblicalContext['roman_presence']
  sacred_representation_policy: '' | BiblicalContext['sacred_representation_policy']
  angel_policy: '' | BiblicalContext['angel_policy']
  miracle_intensity: '' | BiblicalContext['miracle_intensity']
}

export const CREATIVE_THEMES: Array<{
  id: CreativeThemeId
  label: string
  description: string
}> = [
  { id: 'default', label: 'Default', description: 'Current CineForge setup.' },
  {
    id: 'greek_mythology',
    label: 'Greek Mythology Theme',
    description: 'Grounded live-action ancient Greek mythology.',
  },
  {
    id: 'biblical',
    label: 'Biblical Theme',
    description: 'Source-faithful, historically grounded biblical cinema.',
  },
]

export const EMPTY_BIBLICAL_CONTEXT: BiblicalContextDraft = {
  canon_context: '',
  scripture_reference: '',
  narrative_period: '',
  historical_preset: '',
  region: '',
  culture: '',
  roman_presence: '',
  sacred_representation_policy: '',
  angel_policy: '',
  miracle_intensity: '',
}

export function biblicalContextPayload(draft: BiblicalContextDraft): BiblicalContext | null {
  const culture = draft.culture.split(',').map((item) => item.trim()).filter(Boolean)
  if (
    !draft.canon_context ||
    !draft.narrative_period.trim() ||
    !draft.historical_preset ||
    !draft.region.trim() ||
    !culture.length ||
    !draft.roman_presence ||
    !draft.sacred_representation_policy ||
    !draft.angel_policy ||
    !draft.miracle_intensity
  ) return null
  return {
    canon_context: draft.canon_context,
    scripture_reference: draft.scripture_reference.trim() || null,
    narrative_period: draft.narrative_period.trim(),
    historical_preset: draft.historical_preset,
    region: draft.region.trim(),
    culture,
    roman_presence: draft.roman_presence,
    sacred_representation_policy: draft.sacred_representation_policy,
    angel_policy: draft.angel_policy,
    miracle_intensity: draft.miracle_intensity,
  }
}

export function biblicalContextDraft(context: BiblicalContext | null | undefined): BiblicalContextDraft {
  if (!context) return { ...EMPTY_BIBLICAL_CONTEXT }
  return {
    canon_context: context.canon_context,
    scripture_reference: context.scripture_reference ?? '',
    narrative_period: context.narrative_period,
    historical_preset: context.historical_preset,
    region: context.region,
    culture: context.culture.join(', '),
    roman_presence: context.roman_presence,
    sacred_representation_policy: context.sacred_representation_policy,
    angel_policy: context.angel_policy,
    miracle_intensity: context.miracle_intensity,
  }
}

export function creativeThemeLabel(themeId: CreativeThemeId): string {
  return CREATIVE_THEMES.find((theme) => theme.id === themeId)?.label ?? 'Default'
}
