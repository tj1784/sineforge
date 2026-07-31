import type { OrchestrationStep, ProviderCatalogEntry } from '../api/client'

const LOCAL_PROVIDER_LABELS: Record<string, string> = {
  qwen: 'Qwen3 4B Hivemind',
  sulphur: 'Sulphur 2 Base',
  mock: 'Built-in mock',
  openai: 'OpenAI',
}

function profileFromResolvedModel(value: string | null | undefined): string | null {
  const match = value?.match(/(?:^|:)logical\/(luna|terra|sol)$/i)
  return match?.[1]?.toLowerCase() ?? null
}

function formatLogicalProfile(value: string | null | undefined): string | null {
  if (!value) return null
  return `${value.charAt(0).toUpperCase()}${value.slice(1).toLowerCase()} profile`
}

export function formatPlanningRoute(
  step:
    | Pick<OrchestrationStep, 'provider_identifier' | 'logical_model' | 'resolved_model'>
    | null
    | undefined,
  providerCatalog: ProviderCatalogEntry[] = [],
): string {
  if (!step) return 'Not selected'

  const providerIdentifier = step.provider_identifier?.trim()
  if (!providerIdentifier) return 'Not selected'

  const providerFact = providerCatalog.find(
    (provider) => provider.provider_identifier === providerIdentifier,
  )
  const providerLabel =
    LOCAL_PROVIDER_LABELS[providerIdentifier] ?? providerFact?.display_name ?? providerIdentifier

  const resolvedModel = step.resolved_model?.trim() || null
  const logicalProfile =
    formatLogicalProfile(step.logical_model) ??
    formatLogicalProfile(profileFromResolvedModel(resolvedModel))

  if (resolvedModel && !profileFromResolvedModel(resolvedModel)) {
    return `${providerLabel} · ${resolvedModel}`
  }

  return logicalProfile ? `${providerLabel} · ${logicalProfile}` : providerLabel
}
