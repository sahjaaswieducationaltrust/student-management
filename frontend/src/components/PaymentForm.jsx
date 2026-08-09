import { useMemo, useState } from 'react'
import api, { errorMessage } from '../lib/api'
import {
  CUSTOM_PARTICULARS,
  FEE_PARTICULARS,
  PAYMENT_MODES,
  formatDate,
  money,
  toInputDate,
  today,
} from '../lib/format'
import { Field, Modal } from './ui'
import { useToast } from './Toast'

/**
 * Collect a fee payment. The backend decides which installments the money is
 * applied to (earliest due first) and issues the receipt number.
 */
export default function PaymentForm({ ledger, onClose, onPaid }) {
  const toast = useToast()
  const suggested = ledger?.next_due?.balance ?? ledger?.balance ?? 0

  const [form, setForm] = useState({
    amount: suggested > 0 ? String(suggested) : '',
    mode: 'cash',
    paid_on: today(),
    reference: '',
    remarks: '',
    particulars: '',
    custom_particulars: '',
    // Blank means "keep the automatic schedule". Pre-filled with whatever
    // override is already on the record so reopening the dialog does not
    // silently drop a date the desk agreed earlier.
    next_due_date: toInputDate(ledger?.next_due_override) || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const amount = Number(form.amount || 0)
  const balanceAfter = useMemo(() => (ledger?.balance ?? 0) - amount, [ledger, amount])
  const needsReference = ['cheque', 'bank_transfer', 'upi', 'card'].includes(form.mode)

  // Blank means "let the backend describe it from the schedule".
  const particulars =
    form.particulars === CUSTOM_PARTICULARS ? form.custom_particulars.trim() : form.particulars

  const submit = async (event) => {
    event.preventDefault()
    if (amount <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    if (form.particulars === CUSTOM_PARTICULARS && !particulars) {
      setError('Type what this payment is for, or pick one of the listed particulars.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post('/api/fees/payments', {
        student_id: ledger.student_id,
        amount,
        mode: form.mode,
        paid_on: form.paid_on || null,
        reference: form.reference || null,
        remarks: form.remarks || null,
        particulars: particulars || null,
        next_due_date: form.next_due_date || null,
      })
      toast.success(`Receipt ${data.receipt_no} created`)
      onPaid(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Collect fee payment"
      subtitle={`${ledger.student_name} · ${ledger.admission_no}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="payment-form" className="btn primary" disabled={busy}>
            {busy ? <span className="spinner" /> : 'Save & generate receipt'}
          </button>
        </>
      }
    >
      <form id="payment-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        {error && <div className="alert error">{error}</div>}

        <div className="alert info">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span>Total payable</span>
            <b>{money(ledger.net_payable)}</b>
          </div>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span>Paid so far</span>
            <b>{money(ledger.total_paid)}</b>
          </div>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span>Outstanding balance</span>
            <b>{money(ledger.balance)}</b>
          </div>
          {ledger.next_due && (
            <div className="row small" style={{ justifyContent: 'space-between', marginTop: 4 }}>
              <span>
                Next instalment · {ledger.next_due.label} (due {formatDate(ledger.next_due.due_date)})
              </span>
              <b>{money(ledger.next_due.balance)}</b>
            </div>
          )}
        </div>

        <div className="form-grid">
          <Field label="Amount received" required hint={ledger.next_due ? 'Pre-filled with the next instalment' : undefined}>
            <input
              type="number"
              min="1"
              step="0.01"
              required
              autoFocus
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </Field>
          <Field label="Payment mode" required>
            <select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
              {PAYMENT_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Paid towards"
            className={form.particulars === CUSTOM_PARTICULARS ? '' : 'full'}
            hint="Printed as the particulars on the receipt"
          >
            <select
              value={form.particulars}
              onChange={(e) => setForm({ ...form, particulars: e.target.value })}
            >
              {FEE_PARTICULARS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          {form.particulars === CUSTOM_PARTICULARS && (
            <Field label="Particulars" required>
              <input
                required
                maxLength={120}
                value={form.custom_particulars}
                onChange={(e) => setForm({ ...form, custom_particulars: e.target.value })}
                placeholder="e.g. Annual Day charges"
              />
            </Field>
          )}
          <Field label="Payment date">
            <input type="date" max={today()} value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} />
          </Field>
          <Field
            label="Reference no."
            hint={needsReference ? 'Cheque / UPI / transaction reference' : 'Optional'}
          >
            <input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          </Field>
          <Field
            label="Next instalment due on"
            hint="Leave blank to keep the automatic schedule"
          >
            <input
              type="date"
              value={form.next_due_date}
              onChange={(e) => setForm({ ...form, next_due_date: e.target.value })}
            />
          </Field>
          <Field label="Remarks" className="full">
            <input
              value={form.remarks}
              onChange={(e) => setForm({ ...form, remarks: e.target.value })}
              placeholder="e.g. Initial admission payment"
            />
          </Field>
        </div>

        {amount > 0 && (
          <div className={`alert ${balanceAfter > 0 ? '' : 'success'}`} style={balanceAfter > 0 ? { background: '#fafbfd', border: '1px dashed var(--line)' } : undefined}>
            Balance after this payment: <b>{money(Math.max(0, balanceAfter))}</b>
            {balanceAfter < 0 && <span className="muted"> (includes {money(-balanceAfter)} advance)</span>}
          </div>
        )}
      </form>
    </Modal>
  )
}
