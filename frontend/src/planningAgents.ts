export const LOCAL_PLANNING_AGENTS = [
  {
    value: 'qwen',
    label: 'Qwen3 4B Hivemind',
    description:
      'Fast local creative planner for Phase 1 structured story, scene, shot, and prompt planning.',
    runtime: 'local Q4_K_M',
  },
  {
    value: 'sulphur',
    label: 'Sulphur 2 Base',
    description:
      'Fast local specialist for structured project intake, scripts, and production briefs.',
    runtime: 'local Q8_0',
  },
] as const

export type PlanningAgent = (typeof LOCAL_PLANNING_AGENTS)[number]['value']

export function localPlanningAgent(
  agent: PlanningAgent | null | undefined,
) {
  return LOCAL_PLANNING_AGENTS.find((option) => option.value === agent)
}
