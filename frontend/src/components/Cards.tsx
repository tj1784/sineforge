import { StatusBadge } from './StatusBadge'

type StatusCardProps = {
  title: string
  status?: string | boolean | null
  detail: string
  meta?: string
}

export function StatusCard({ title, status, detail, meta }: StatusCardProps) {
  return (
    <article className="card status-card">
      <div className="card-heading">
        <span>{title}</span>
        <StatusBadge status={status} />
      </div>
      <p>{detail}</p>
      {meta ? <small>{meta}</small> : null}
    </article>
  )
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  )
}

export function ErrorNotice({
  message,
  actionLabel,
  onAction,
}: {
  message: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="notice error" role="alert">
      <span>{message}</span>
      {actionLabel && onAction ? (
        <button type="button" className="btn secondary" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}

export function SuccessNotice({ message }: { message: string }) {
  return <div className="notice success">{message}</div>
}

export function DebugPanel({ title, data }: { title: string; data: unknown }) {
  return (
    <details className="debug-panel">
      <summary>{title}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  )
}
