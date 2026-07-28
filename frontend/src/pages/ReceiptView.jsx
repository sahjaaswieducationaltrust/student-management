import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { Empty, Field, Loading, Modal } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { downloadReceiptPdf, errorMessage } from '../lib/api'
import { formatDate, modeLabel, money } from '../lib/format'

function CancelDialog({ payment, onClose, onCancelled }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      await api.post(`/api/fees/payments/${payment.id}/cancel`, null, { params: { reason } })
      toast.success('Receipt cancelled')
      onCancelled()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Cancel this receipt?"
      subtitle={payment.receipt_no}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Keep it
          </button>
          <button className="btn danger" type="submit" form="cancel-form" disabled={busy || reason.trim().length < 3}>
            {busy ? <span className="spinner" /> : 'Cancel receipt'}
          </button>
        </>
      }
    >
      <form id="cancel-form" onSubmit={submit} className="stack" style={{ gap: 12 }}>
        <div className="alert error">
          The amount stops counting towards the child's paid total. The receipt stays on record,
          marked as cancelled.
        </div>
        <Field label="Reason" required>
          <input
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Cheque bounced, entered twice…"
          />
        </Field>
      </form>
    </Modal>
  )
}

export default function ReceiptView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { isAdmin } = useAuth()
  const [receipt, setReceipt] = useState(null)
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get(`/api/fees/receipts/${id}`)
      setReceipt(data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [id, toast])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <Loading />
  if (!receipt) return <Empty icon="🔍" title="Receipt not found" />

  const { payment, school } = receipt

  return (
    <div className="stack">
      <div className="row no-print">
        <button className="btn" onClick={() => navigate(-1)}>
          ← Back
        </button>
        <div className="spacer" />
        <button className="btn" onClick={() => window.print()}>
          🖨️ Print
        </button>
        <button
          className="btn"
          onClick={() => downloadReceiptPdf(payment.id, payment.receipt_no).catch((err) => toast.error(errorMessage(err)))}
        >
          ⬇️ Download PDF
        </button>
        <Link className="btn primary" to={`/students/${payment.student_id}`}>
          Child profile
        </Link>
        {isAdmin && !payment.cancelled && (
          <button className="btn danger" onClick={() => setCancelling(true)}>
            Cancel receipt
          </button>
        )}
      </div>

      <div className="receipt-sheet">
        <header className="receipt-head">
          <div className="mark">
            <img src="/hellokids-logo.png" alt="" />
          </div>
          <div className="who">
            <h2>{school.name}</h2>
            {school.tagline && <div className="tagline">{school.tagline}</div>}
            <div className="addr">{school.address}</div>
            <div className="addr">
              Phone: {school.phone} · {school.email}
              {school.website ? ` · ${school.website}` : ''}
            </div>
          </div>
          <div className="rule" />
        </header>

        <div className={`receipt-title ${payment.cancelled ? 'cancelled' : ''}`}>
          {payment.cancelled ? 'FEE RECEIPT — CANCELLED' : 'FEE RECEIPT'}
        </div>

        <div className="receipt-meta">
          <div className="m">
            <span>Receipt No.</span>
            <b>{payment.receipt_no}</b>
          </div>
          <div className="m">
            <span>Date</span>
            <b>{formatDate(payment.paid_on)}</b>
          </div>
          <div className="m">
            <span>Admission No.</span>
            <b>{payment.admission_no}</b>
          </div>
          <div className="m">
            <span>Academic Year</span>
            <b>{payment.academic_year}</b>
          </div>
          <div className="m">
            <span>Child's Name</span>
            <b>{payment.student_name}</b>
          </div>
          <div className="m">
            <span>Class</span>
            <b>{payment.classroom_name || '—'}</b>
          </div>
          <div className="m">
            <span>Payment Mode</span>
            <b>{modeLabel(payment.mode)}</b>
          </div>
          <div className="m">
            <span>Reference</span>
            <b>{payment.reference || '—'}</b>
          </div>
        </div>

        <table className="receipt-items">
          <thead>
            <tr>
              <th style={{ width: 44 }}>#</th>
              <th>Particulars</th>
              <th style={{ width: 140 }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {(payment.items?.length ? payment.items : [{ name: 'Fee payment', amount: payment.amount }]).map(
              (item, index) => (
                <tr key={`${item.name}-${index}`}>
                  <td>{index + 1}</td>
                  <td>{item.name}</td>
                  <td>{money(item.amount)}</td>
                </tr>
              ),
            )}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2}>Total received</td>
              <td>{money(payment.amount)}</td>
            </tr>
          </tfoot>
        </table>

        <div className="receipt-words">
          <b>In words:</b> {receipt.amount_in_words}
        </div>

        <div className="receipt-summary">
          <div className="r">
            <span>Total fee payable</span>
            <b>{money(receipt.net_payable)}</b>
          </div>
          <div className="r">
            <span>Paid till date</span>
            <b>{money(receipt.total_paid)}</b>
          </div>
          <div className="r total">
            <span>Balance due</span>
            <b>{money(receipt.balance)}</b>
          </div>
        </div>

        {payment.remarks && (
          <p className="small muted" style={{ marginTop: 16 }}>
            <b>Remarks:</b> {payment.remarks}
          </p>
        )}
        {payment.cancelled && (
          <p className="small text-red" style={{ marginTop: 10 }}>
            <b>This receipt has been cancelled.</b> {payment.cancel_reason}
          </p>
        )}

        <footer className="receipt-foot">
          <div>
            Received by: {payment.collected_by || '—'}
            <br />
            This is a computer generated receipt.
          </div>
          <div className="sign">
            <div className="line">Authorised Signatory</div>
          </div>
        </footer>
      </div>

      {cancelling && (
        <CancelDialog
          payment={payment}
          onClose={() => setCancelling(false)}
          onCancelled={() => {
            setCancelling(false)
            load()
          }}
        />
      )}
    </div>
  )
}
