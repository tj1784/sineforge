import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type PageContextEnvelope } from '../api/client'
import { OperatorChatLauncher } from './OperatorChat'
import { OperatorContextProvider } from './OperatorContext'

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 500
    detail = null
  },
  api: {
    getAgentProviderHealth: vi.fn(),
    createAgentSession: vi.fn(),
    sendAgentMessage: vi.fn(),
    approveAgentProposal: vi.fn(),
    rejectAgentProposal: vi.fn(),
    undoAgentAction: vi.fn(),
  },
}))

const storyRecordId = '87654321-4321-4321-4321-cba987654321'

const baseContext: PageContextEnvelope = {
  contextVersion: 1,
  capturedAt: '2026-07-31T12:00:00.000Z',
  routeId: 'studio.story',
  pathname: '/projects/project-123/studio/story',
  pageViewId: 'pageview-test',
  pageTitle: 'Project Story',
  domain: 'studio',
  tenantId: 'local-workspace',
  projectId: '12345678-1234-1234-1234-123456789abc',
  projectVersion: 'v1',
  recordType: 'story',
  recordId: storyRecordId,
  recordVersion: 'story-v1',
  parentRefs: [],
  selectedRefs: [{ type: 'story', id: storyRecordId }],
  activeTab: 'story',
  activePanel: null,
  filters: {},
  mode: 'view',
  dirty: false,
  capabilities: ['context.get_current', 'project.get', 'review.add_note'],
  correlationId: 'initial-correlation',
}

function renderOperator() {
  render(
    <OperatorContextProvider baseContext={baseContext}>
      <OperatorChatLauncher />
    </OperatorContextProvider>,
  )
}

beforeEach(() => {
  vi.mocked(api.getAgentProviderHealth).mockResolvedValue({
    enabled: true,
    provider: 'openai_compatible',
    base_url: 'http://127.0.0.1:1234/v1',
    configured_model: 'qwen-local',
    reachable: true,
    status: 'ok',
    model_count: 1,
    active_model_id: 'qwen-local',
    error: null,
    capabilities: { streaming: true, structured_output: true, native_tool_calling: false },
  })
  vi.mocked(api.createAgentSession).mockResolvedValue({
    id: 'session-1',
    actor_id: 'local-user',
    title: 'CineForge Operator',
    provider: 'openai_compatible',
    model: 'qwen-local',
    status: 'active',
    created_at: '2026-07-31T12:00:00Z',
    updated_at: '2026-07-31T12:00:00Z',
  })
  vi.mocked(api.sendAgentMessage).mockResolvedValue({
    session: {
      id: 'session-1',
      actor_id: 'local-user',
      title: 'CineForge Operator',
      provider: 'openai_compatible',
      model: 'qwen-local',
      status: 'active',
      created_at: '2026-07-31T12:00:00Z',
      updated_at: '2026-07-31T12:00:01Z',
    },
    user_message: {
      id: 'message-user',
      session_id: 'session-1',
      role: 'user',
      content: 'Add a review note',
      status: 'complete',
      created_at: '2026-07-31T12:00:00Z',
      metadata: {},
    },
    assistant_message: {
      id: 'message-assistant',
      session_id: 'session-1',
      role: 'assistant',
      content: 'Approval required for `review.add_note`.',
      status: 'complete',
      created_at: '2026-07-31T12:00:01Z',
      metadata: {},
    },
    context_snapshot: {
      id: 'snapshot-1',
      context_hash: 'hash',
      context: baseContext,
      hydrated_summary: {},
      source_refs: [],
    },
    provider_health: {
      enabled: true,
      provider: 'openai_compatible',
      base_url: 'http://127.0.0.1:1234/v1',
      configured_model: 'qwen-local',
      reachable: true,
      status: 'ok',
      model_count: 1,
      active_model_id: 'qwen-local',
      error: null,
      capabilities: { streaming: true, structured_output: true, native_tool_calling: false },
    },
    tool_activities: [
      {
        id: 'tool-1',
        name: 'review.add_note',
        status: 'approval_required',
        risk_class: 'low',
        target: { type: 'story', id: storyRecordId, version: 'story-v1' },
        validation: { allowed: true },
        result: { status: 'approval_required', proposal_id: 'proposal-1' },
        error: null,
      },
    ],
    proposals: [
      {
        id: 'proposal-1',
        session_id: 'session-1',
        tool_name: 'review.add_note',
        proposal_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
        target_type: 'story',
        target_id: storyRecordId,
        target_version: 'story-v1',
        status: 'pending_approval',
        arguments: { note: 'Check transition.' },
        validation: { allowed: true },
        approval_required: true,
        approval_token: 'approval-token-1234567890',
        approval_expires_at: '2026-07-31T12:10:00Z',
        created_at: '2026-07-31T12:00:01Z',
      },
    ],
    receipts: [],
  })
  vi.mocked(api.approveAgentProposal).mockResolvedValue({
    id: 'receipt-1',
    session_id: 'session-1',
    proposal_id: 'proposal-1',
    action: 'review.add_note',
    actor_id: 'local-user',
    target_type: 'story',
    target_id: storyRecordId,
    target_version_before: 'story-v1',
    target_version_after: 'story-v1',
    result_resource_type: 'creative_review_note',
    result_resource_id: 'note-1',
    status: 'succeeded',
    undo_status: 'available',
    result: { review_note_id: 'note-1', note: 'Check transition.' },
    undo: { strategy: 'delete_created_review_note' },
    created_at: '2026-07-31T12:00:02Z',
  })
  vi.mocked(api.undoAgentAction).mockResolvedValue({
    id: 'receipt-1',
    session_id: 'session-1',
    proposal_id: 'proposal-1',
    action: 'review.add_note',
    actor_id: 'local-user',
    target_type: 'story',
    target_id: storyRecordId,
    target_version_before: 'story-v1',
    target_version_after: 'story-v1',
    result_resource_type: 'creative_review_note',
    result_resource_id: 'note-1',
    status: 'succeeded',
    undo_status: 'completed',
    result: { review_note_id: 'note-1', note: 'Check transition.' },
    undo: { strategy: 'delete_created_review_note', undone_by: 'local-user' },
    created_at: '2026-07-31T12:00:02Z',
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('OperatorChatLauncher', () => {
  it('captures context, shows approval cards, and executes approval plus undo', async () => {
    renderOperator()
    fireEvent.click(screen.getByRole('button', { name: 'Open CineForge Operator' }))

    expect(await screen.findByText('qwen-local')).toBeTruthy()
    expect(screen.getByText('/projects/project-123/studio/story')).toBeTruthy()

    const thinkingToggle = screen.getByRole('button', { name: 'Turn thinking off' })
    expect(thinkingToggle.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(thinkingToggle)
    expect(screen.getByRole('button', { name: 'Turn thinking on' }).getAttribute('aria-pressed')).toBe('false')

    fireEvent.change(screen.getByLabelText('Message CineForge Operator'), {
      target: { value: 'Add a review note' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(api.sendAgentMessage).toHaveBeenCalled())
    const sentPayload = vi.mocked(api.sendAgentMessage).mock.calls[0][1]
    expect(sentPayload.context.recordId).toBe(baseContext.recordId)
    expect(sentPayload.context.correlationId).not.toBe('initial-correlation')
    expect(sentPayload.thinking_enabled).toBe(false)
    expect(await screen.findByText('+ Check transition.')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(api.approveAgentProposal).toHaveBeenCalledWith(
      'proposal-1',
      expect.objectContaining({ approval_token: 'approval-token-1234567890' }),
    ))
    expect(await screen.findByText(/review_note_id/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(api.undoAgentAction).toHaveBeenCalledWith(
      'receipt-1',
      expect.objectContaining({ actor_id: 'local-user' }),
    ))
  })
})
