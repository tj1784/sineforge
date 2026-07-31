export const PROJECT_WORKFLOW_LANES = [
  {
    value: 'cineforge_studio',
    label: 'CineForge Studio Workflow',
    description:
      'Use CineForge planning and creative agents, including optional Sulphur-assisted project intake.',
  },
  {
    value: 'agentless',
    label: 'Agentless Workflow',
    description:
      'Block hosted/API agents while using a selected local agent for planning and deterministic scene-reset production.',
  },
] as const

export type ProjectWorkflowLane = (typeof PROJECT_WORKFLOW_LANES)[number]['value']

export function projectWorkflowLaneLabel(
  lane: ProjectWorkflowLane | null | undefined,
): string {
  return (
    PROJECT_WORKFLOW_LANES.find((option) => option.value === lane)?.label ??
    'Workflow lane not recorded'
  )
}
