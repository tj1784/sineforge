import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import {
  ApiError,
  api,
  type AgentActionReceipt,
  type AgentProposal,
  type AgentProviderHealth,
  type AgentSession,
  type AgentToolActivity,
} from '../api/client'
import { useOptionalOperatorContext, type OperatorContextValue } from './OperatorContext'

type TranscriptItem =
  | { type: 'message'; id: string; role: 'user' | 'assistant'; content: string }
  | { type: 'tool'; id: string; activity: AgentToolActivity }
  | { type: 'proposal'; id: string; proposal: AgentProposal }
  | { type: 'receipt'; id: string; receipt: AgentActionReceipt }
  | { type: 'error'; id: string; content: string }

function randomId(prefix: string) {
  const generated =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  return `${prefix}-${generated}`
}

function compactTarget(proposal: AgentProposal) {
  const id = proposal.target_id ? proposal.target_id.slice(0, 8) : 'none'
  return `${proposal.target_type}:${id}`
}

function noteFromProposal(proposal: AgentProposal) {
  const note = proposal.arguments.note
  return typeof note === 'string' ? note : JSON.stringify(proposal.arguments)
}

function providerLabel(health: AgentProviderHealth | null) {
  if (!health) return 'Checking provider'
  if (!health.enabled) return 'Operator disabled'
  if (!health.reachable) return 'LM Studio offline'
  return health.active_model_id || health.configured_model
}

function messageFromError(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'The operator request failed.'
}

export function OperatorChatLauncher() {
  const operatorContext = useOptionalOperatorContext()
  if (!operatorContext) return null
  return <OperatorChatPanel operatorContext={operatorContext} />
}

function OperatorChatPanel({ operatorContext }: { operatorContext: OperatorContextValue }) {
  const [open, setOpen] = useState(false)
  const [session, setSession] = useState<AgentSession | null>(null)
  const [health, setHealth] = useState<AgentProviderHealth | null>(null)
  const [items, setItems] = useState<TranscriptItem[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [thinkingEnabled, setThinkingEnabled] = useState(true)
  const [approvingId, setApprovingId] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const context = operatorContext.context
  const captureContext = operatorContext.captureContext
  const contextTitle = useMemo(() => {
    if (!context) return 'Workspace'
    const project = context.projectId ? `Project ${context.projectId.slice(0, 8)}` : 'Workspace'
    const record =
      context.recordType && context.recordId
        ? `${context.recordType} ${context.recordId.slice(0, 8)}`
        : context.activeTab || context.routeId
    return `${project} > ${record}`
  }, [context])

  useEffect(() => {
    let cancelled = false
    void api
      .getAgentProviderHealth()
      .then((next) => {
        if (!cancelled) setHealth(next)
      })
      .catch(() => {
        if (!cancelled) {
          setHealth({
            enabled: false,
            provider: 'openai_compatible',
            base_url: '',
            configured_model: '',
            reachable: false,
            status: 'unavailable',
            model_count: 0,
            active_model_id: null,
            error: 'Agent provider health is unavailable.',
            capabilities: {},
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  useEffect(() => {
    const list = listRef.current
    if (list && typeof list.scrollTo === 'function') {
      list.scrollTo({ top: list.scrollHeight })
    }
  }, [items])

  const ensureSession = async () => {
    if (session) return session
    const captured = captureContext()
    const created = await api.createAgentSession({
      actor_id: 'local-user',
      title: 'CineForge Operator',
      context: captured,
    })
    setSession(created)
    return created
  }

  const send = async () => {
    const content = draft.trim()
    if (!content || busy) return
    const captured = captureContext()
    setDraft('')
    setBusy(true)
    const localUser: TranscriptItem = {
      type: 'message',
      id: randomId('local-user'),
      role: 'user',
      content,
    }
    setItems((current) => [...current, localUser])
    try {
      const activeSession = await ensureSession()
      const response = await api.sendAgentMessage(activeSession.id, {
        actor_id: 'local-user',
        content,
        context: captured,
        thinking_enabled: thinkingEnabled,
        idempotency_key: randomId('operator-message'),
      })
      setHealth(response.provider_health)
      const assistant: TranscriptItem = {
        type: 'message',
        id: response.assistant_message.id,
        role: 'assistant',
        content: response.assistant_message.content,
      }
      const activities = response.tool_activities.map<TranscriptItem>((activity) => ({
        type: 'tool',
        id: activity.id ?? randomId('tool'),
        activity,
      }))
      const proposals = response.proposals.map<TranscriptItem>((proposal) => ({
        type: 'proposal',
        id: proposal.id,
        proposal,
      }))
      const receipts = response.receipts.map<TranscriptItem>((receipt) => ({
        type: 'receipt',
        id: receipt.id,
        receipt,
      }))
      setItems((current) => [...current, assistant, ...activities, ...proposals, ...receipts])
    } catch (error) {
      setItems((current) => [
        ...current,
        { type: 'error', id: randomId('error'), content: messageFromError(error) },
      ])
    } finally {
      setBusy(false)
    }
  }

  const approve = async (proposal: AgentProposal) => {
    if (!proposal.approval_token || approvingId) return
    setApprovingId(proposal.id)
    try {
      const receipt = await api.approveAgentProposal(proposal.id, {
        actor_id: 'local-user',
        approval_token: proposal.approval_token,
        idempotency_key: randomId('operator-approval'),
      })
      setItems((current) => [
        ...current,
        { type: 'receipt', id: receipt.id, receipt },
      ])
    } catch (error) {
      setItems((current) => [
        ...current,
        { type: 'error', id: randomId('error'), content: messageFromError(error) },
      ])
    } finally {
      setApprovingId(null)
    }
  }

  const reject = async (proposal: AgentProposal) => {
    if (approvingId) return
    setApprovingId(proposal.id)
    try {
      const rejected = await api.rejectAgentProposal(proposal.id, {
        actor_id: 'local-user',
        reason: 'Rejected from Operator panel',
      })
      setItems((current) => [
        ...current,
        { type: 'proposal', id: `${rejected.id}:rejected`, proposal: rejected },
      ])
    } catch (error) {
      setItems((current) => [
        ...current,
        { type: 'error', id: randomId('error'), content: messageFromError(error) },
      ])
    } finally {
      setApprovingId(null)
    }
  }

  const undo = async (receipt: AgentActionReceipt) => {
    if (approvingId || receipt.undo_status !== 'available') return
    setApprovingId(receipt.id)
    try {
      const undone = await api.undoAgentAction(receipt.id, {
        actor_id: 'local-user',
        reason: 'Undo from Operator panel',
      })
      setItems((current) => [
        ...current,
        { type: 'receipt', id: `${undone.id}:undo`, receipt: undone },
      ])
    } catch (error) {
      setItems((current) => [
        ...current,
        { type: 'error', id: randomId('error'), content: messageFromError(error) },
      ])
    } finally {
      setApprovingId(null)
    }
  }

  const handlePanelKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab' || !panelRef.current) return
    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(
        'button, textarea, input, select, details, [href], [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((node) => !node.hasAttribute('disabled'))
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <>
      <button
        type="button"
        className="operator-launcher"
        aria-label="Open CineForge Operator"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">CF</span>
        <b>Operator</b>
      </button>

      {open ? (
        <div
          className="operator-panel"
          role="dialog"
          aria-modal="true"
          aria-label="CineForge Operator"
          ref={panelRef}
          onKeyDown={handlePanelKeyDown}
        >
          <header className="operator-header">
            <div>
              <strong>CineForge Operator</strong>
              <small>{providerLabel(health)}</small>
            </div>
            <div className="operator-header-actions">
              <button
                type="button"
                className={`operator-thinking-toggle ${thinkingEnabled ? 'active' : ''}`}
                aria-label={`Turn thinking ${thinkingEnabled ? 'off' : 'on'}`}
                aria-pressed={thinkingEnabled}
                title={thinkingEnabled ? 'Thinking is enabled' : 'Thinking is disabled'}
                onClick={() => setThinkingEnabled((value) => !value)}
              >
                <span aria-hidden="true">◈</span>
                Thinking {thinkingEnabled ? 'on' : 'off'}
              </button>
              <button type="button" aria-label="Close CineForge Operator" onClick={() => setOpen(false)}>
                x
              </button>
            </div>
          </header>

          <section className="operator-context-card" aria-label="Active operator context">
            <span>{contextTitle}</span>
            <small>{context.pathname}</small>
            <details>
              <summary>Context inspector</summary>
              <pre>{JSON.stringify(context, null, 2)}</pre>
            </details>
          </section>

          <div className="operator-transcript" ref={listRef} aria-live="polite">
            {items.length === 0 ? (
              <div className="operator-empty">
                Ask about the current page, project, selected record, or a safe change. Mutations will stop for approval.
              </div>
            ) : null}
            {items.map((item) => {
              if (item.type === 'message') {
                return (
                  <article key={item.id} className={`operator-message ${item.role}`}>
                    <b>{item.role === 'user' ? 'You' : 'Operator'}</b>
                    <p>{item.content}</p>
                  </article>
                )
              }
              if (item.type === 'tool') {
                return (
                  <article key={item.id} className="operator-activity">
                    <header>
                      <b>{item.activity.name}</b>
                      <span>{item.activity.status}</span>
                    </header>
                    <small>Risk: {item.activity.risk_class}</small>
                    {item.activity.error ? <p>{item.activity.error}</p> : null}
                    {Object.keys(item.activity.result).length ? (
                      <pre>{JSON.stringify(item.activity.result, null, 2)}</pre>
                    ) : null}
                  </article>
                )
              }
              if (item.type === 'proposal') {
                const proposal = item.proposal
                return (
                  <article key={item.id} className="operator-proposal">
                    <header>
                      <b>{proposal.tool_name}</b>
                      <span>{proposal.status}</span>
                    </header>
                    <small>{compactTarget(proposal)}</small>
                    <div className="operator-diff">
                      <span>+ {noteFromProposal(proposal)}</span>
                    </div>
                    <dl>
                      <dt>Target version</dt>
                      <dd>{proposal.target_version ?? 'none'}</dd>
                      <dt>Proposal hash</dt>
                      <dd>{proposal.proposal_hash.slice(0, 16)}</dd>
                    </dl>
                    {proposal.status === 'pending_approval' && proposal.approval_token ? (
                      <div className="operator-card-actions">
                        <button
                          type="button"
                          onClick={() => void approve(proposal)}
                          disabled={approvingId === proposal.id}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => void reject(proposal)}
                          disabled={approvingId === proposal.id}
                        >
                          Reject
                        </button>
                      </div>
                    ) : null}
                  </article>
                )
              }
              if (item.type === 'receipt') {
                const receipt = item.receipt
                return (
                  <article key={item.id} className="operator-receipt">
                    <header>
                      <b>{receipt.action}</b>
                      <span>{receipt.status}</span>
                    </header>
                    <small>
                      {receipt.result_resource_type ?? 'resource'}:{' '}
                      {receipt.result_resource_id?.slice(0, 8) ?? 'none'}
                    </small>
                    <pre>{JSON.stringify(receipt.result, null, 2)}</pre>
                    {receipt.undo_status === 'available' ? (
                      <button type="button" onClick={() => void undo(receipt)} disabled={approvingId === receipt.id}>
                        Undo
                      </button>
                    ) : (
                      <small>Undo: {receipt.undo_status}</small>
                    )}
                  </article>
                )
              }
              return (
                <article key={item.id} className="operator-error" role="alert">
                  {item.content}
                </article>
              )
            })}
          </div>

          <footer className="operator-composer">
            <textarea
              ref={inputRef}
              value={draft}
              aria-label="Message CineForge Operator"
              placeholder="Ask about this page or propose a safe change..."
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault()
                  void send()
                }
              }}
            />
            <button type="button" onClick={() => void send()} disabled={busy || !draft.trim()}>
              {busy ? 'Working' : 'Send'}
            </button>
          </footer>
        </div>
      ) : null}
    </>
  )
}
