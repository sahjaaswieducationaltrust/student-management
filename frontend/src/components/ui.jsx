import { useEffect } from 'react'

export function Card({ title, subtitle, actions, children, bodyClass = '', className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <div className="small muted">{subtitle}</div>}
          </div>
          {actions && <div className="spacer" />}
          {actions}
        </header>
      )}
      <div className={`card-body ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function Field({ label, required, hint, error, children, className = '' }) {
  return (
    <div className={`field ${className}`}>
      {label && (
        <label>
          {label} {required && <span className="req">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <span className="help">{hint}</span>}
      {error && <span className="help text-red">{error}</span>}
    </div>
  )
}

export function Modal({ title, subtitle, size = '', onClose, footer, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className="modal-backdrop no-print" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`modal ${size}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <div className="small muted">{subtitle}</div>}
          </div>
          <button type="button" className="x" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}

export function Confirm({ title = 'Are you sure?', message, confirmLabel = 'Confirm', danger, busy, onConfirm, onClose }) {
  return (
    <Modal
      title={title}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={onConfirm} disabled={busy}>
            {busy ? <span className="spinner" /> : confirmLabel}
          </button>
        </>
      }
    >
      <p className="muted">{message}</p>
    </Modal>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading-block">
      <div style={{ textAlign: 'center' }}>
        <span className="spinner" />
        <div className="small muted" style={{ marginTop: 8 }}>
          {label}
        </div>
      </div>
    </div>
  )
}

export function Empty({ icon = '🗂️', title = 'Nothing here yet', hint, action }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  )
}

export function Badge({ tone = '', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function StatCard({ icon, label, value, hint, tone = '' }) {
  return (
    <div className="stat">
      <div className="stat-ico" style={tone ? { background: tone } : undefined}>
        {icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="label">{label}</div>
        <div className="value">{value}</div>
        {hint && <div className="hint">{hint}</div>}
      </div>
    </div>
  )
}

export function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="pagination">
      <span className="muted">
        Showing {from}–{to} of {total}
      </span>
      <div className="spacer" />
      <button className="btn sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ← Prev
      </button>
      <span className="small muted">
        Page {page} / {pages}
      </span>
      <button className="btn sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Next →
      </button>
    </div>
  )
}

export function StatusBadge({ status }) {
  const tone =
    { active: 'green', present: 'green', paid: 'green', inactive: '', graduated: 'brand', late: 'amber', partial: 'amber', due: 'amber', absent: 'red', overdue: 'red' }[status] ?? ''
  return <Badge tone={tone}>{String(status || '—').replace(/_/g, ' ')}</Badge>
}
