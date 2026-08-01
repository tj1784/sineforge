# CineForge Contextual Operator Agent

This document records the first integrated Contextual Operator implementation.
The operator is embedded in CineForge, uses a backend-owned local
OpenAI-compatible provider connection, and keeps the model behind typed tools.

## Runtime Configuration

Default local configuration:

```text
CINEFORGE_AI_AGENT_ENABLED=false
CINEFORGE_AI_PROVIDER=openai_compatible
CINEFORGE_AI_BASE_URL=http://127.0.0.1:1234/v1
CINEFORGE_AI_MODEL=<LM Studio model id>
CINEFORGE_AI_API_KEY=lm-studio
CINEFORGE_AI_REQUEST_TIMEOUT_SECONDS=120
CINEFORGE_AI_MAX_TOOL_STEPS=12
CINEFORGE_AI_PARALLEL_MODEL_REQUESTS=1
```

The browser never calls LM Studio directly. The backend owns provider health,
model discovery, turn execution, tool validation, proposal creation, approval,
deterministic execution, receipts, undo, and audit events.

## Implementation Ledger

| Capability | Implementation |
|---|---|
| Persistent launcher and drawer | `frontend/src/operator/OperatorChat.tsx`, mounted by `frontend/src/components/AppShell.tsx` |
| Typed page context registry | `frontend/src/operator/OperatorContext.tsx` |
| Studio record adapter | `frontend/src/studio/StudioContext.tsx` registers story/shot context |
| Agent API client | `frontend/src/api/client.ts` agent types and methods |
| LM Studio/OpenAI-compatible provider | `backend/app/services/agent/provider.py` |
| Versioned operator system prompt | `backend/app/services/agent/system_instruction.py` |
| Context hydration and hashing | `backend/app/services/agent/context.py` |
| Tool registry | `backend/app/services/agent/tools.py` |
| Session/message/proposal/approval execution | `backend/app/services/agent/service.py` |
| HTTP API | `backend/app/api/routes/agent.py`, mounted in `backend/app/api/router.py` |
| Persistence | `backend/app/db/base.py`, `backend/alembic/versions/a9b8c7d6e5f4_add_contextual_operator_agent.py` |
| Focused tests | `backend/tests/test_contextual_operator_agent.py`, `frontend/src/operator/OperatorChat.test.tsx` |

## Implemented Tool Surface

Read tools:

- `context.get_current`
- `context.refresh`
- `project.get`
- `project.search`
- `record.get`

Approval-gated mutation:

- `review.add_note`

`review.add_note` creates a proposal first. Approval tokens are returned once
to the UI, stored only as a hash, bound to the proposal hash and target version,
and rejected if the target version changes. Approval creates a
`creative_review_notes` row, an `agent_action_receipts` row, an `audit_logs`
entry, and append-only `agent_audit_events`. Undo deletes only the note created
by that receipt and records the undo in the receipt and audit logs.

## Safety Boundaries

The current implementation deliberately does not expose:

- arbitrary shell commands;
- raw SQL or generic CRUD;
- raw ComfyUI workflow JSON mutation;
- direct ComfyUI prompt submission;
- raw FFmpeg command execution;
- unrestricted filesystem access;
- arbitrary URL/API fetch;
- git commit/push/deploy/restart tools.

The model receives only compact, server-verified context summaries and
server-owned tool schemas. Client-supplied capability claims are stored for
audit but ignored for authorization. Retrieved content is treated as data, not
instructions.

## Provider Behavior

When `CINEFORGE_AI_AGENT_ENABLED=false`, the UI still captures context and shows
the operator as disabled. When LM Studio is offline, the backend returns a
recoverable disconnected state and does not claim a model turn occurred.

When enabled and reachable, the provider is asked for a strict JSON action
envelope:

```json
{
  "assistant_text": "text for the user",
  "tool_call": {
    "name": "project.get",
    "arguments": {}
  }
}
```

Invalid tool names, invalid arguments, forged capabilities, and unavailable
targets are blocked before any executor runs.

## Remaining Extensions

The first production slice implements the contextual shell, LM Studio adapter,
real read tools, one approval-gated reversible write path, receipts, undo, and
audit records. Additional tools should be added only as deterministic services
exist for them. Workspace mutation tools, approved API-catalog calls, generation
enqueueing, workflow parameter proposals, and code patch tools remain disabled
until their policy gates, allowlists, tests, and recovery paths are designed.

