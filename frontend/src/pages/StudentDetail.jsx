import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import PaymentForm from '../components/PaymentForm'
import StudentForm from '../components/StudentForm'
import { useToast } from '../components/Toast'
import { Card, ChildAvatar, Empty, Field, Loading, Modal, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDate, modeLabel, money, titleCase } from '../lib/format'

function FeePlanDialog({ student, ledger, onClose, onSaved }) {
  const toast = useToast()
  const plan = student.fee_plan || {}
  const standard = plan.gross || 0
  const [agreed, setAgreed] = useState(String(plan.net_payable ?? plan.gross ?? ''))
  const [reason, setReason] = useState(plan.discount_reason || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const agreedFee = Number(agreed || 0)
  const difference = agreedFee - standard
  const alreadyPaid = ledger?.total_paid || 0

  const submit = async (event) => {
    event.preventDefault()
    if (agreedFee < alreadyPaid) {
      setError(
        `The agreed fee (${money(agreedFee)}) is less than what has already been paid (${money(alreadyPaid)}).`,
      )
      return
    }
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post(`/api/students/${student.id}/fee-plan`, {
        use_classroom_structure: true,
        agreed_fee: agreedFee,
        discount_reason: reason || null,
      })
      toast.success('Fee plan updated')
      onSaved(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Fee agreement"
      subtitle="Rebuilds the instalment schedule from the agreed total"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" form="feeplan-form" type="submit" disabled={busy}>
            {busy ? <span className="spinner" /> : 'Save fee plan'}
          </button>
        </>
      }
    >
      <form id="feeplan-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        {error && <div className="alert error">{error}</div>}
        <div className="alert info">
          Payments already recorded are <b>not</b> affected — only the schedule of what is still
          due gets regenerated.
        </div>

        <div className="fee-summary-strip">
          <div>
            <span>Standard class fee</span>
            <b>{money(standard)}</b>
          </div>
          <div>
            <span>Already paid</span>
            <b className="text-green">{money(alreadyPaid)}</b>
          </div>
          <div>
            <span>{difference < 0 ? 'Concession' : difference > 0 ? 'Above standard' : 'Difference'}</span>
            <b className={difference < 0 ? 'text-green' : difference > 0 ? 'text-red' : ''}>
              {difference === 0 ? '—' : money(Math.abs(difference))}
            </b>
          </div>
        </div>

        <Field label="Total fee agreed with parents" required>
          <input
            type="number"
            min="0"
            step="0.01"
            required
            autoFocus
            value={agreed}
            onChange={(e) => setAgreed(e.target.value)}
          />
        </Field>
        <Field label="Reason / note">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Sibling concession, staff ward, mid-year admission…"
          />
        </Field>
      </form>
    </Modal>
  )
}

export default function StudentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { canManage } = useAuth()

  const [student, setStudent] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [attendance, setAttendance] = useState(null)
  const [classrooms, setClassrooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('fees')
  const [editing, setEditing] = useState(false)
  const [paying, setPaying] = useState(false)
  const [planning, setPlanning] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, l, a] = await Promise.all([
        api.get(`/api/students/${id}`),
        api.get(`/api/fees/ledger/${id}`),
        api.get(`/api/attendance/student/${id}`, { params: { days: 30 } }),
      ])
      setStudent(s.data)
      setLedger(l.data)
      setAttendance(a.data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [id, toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.get('/api/classrooms').then(({ data }) => setClassrooms(data)).catch(() => {})
  }, [])

  if (loading) return <Loading />
  if (!student) return <Empty icon="🔍" title="Child not found" />

  const g = student.guardian || {}
  const m = student.medical || {}

  return (
    <div className="stack">
      <Card>
        <div className="row" style={{ gap: 16, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          <ChildAvatar gender={student.gender} name={student.full_name} size={60} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="row" style={{ gap: 10 }}>
              <h1>{student.full_name}</h1>
              <StatusBadge status={student.status} />
              {m.allergies && <span className="badge red">⚠ {m.allergies}</span>}
            </div>
            <div className="muted small" style={{ marginTop: 3 }}>
              {student.admission_no} · {student.classroom_name || 'No class assigned'} ·{' '}
              {student.age ? `${student.age} years` : 'Age unknown'} · Joined {formatDate(student.admission_date)}
            </div>
          </div>
          <div className="row no-print">
            <button className="btn" onClick={() => navigate('/students')}>
              ← Back
            </button>
            {canManage && (
              <>
                <button className="btn" onClick={() => setEditing(true)}>
                  Edit
                </button>
                <button className="btn primary" onClick={() => setPaying(true)}>
                  💳 Collect fee
                </button>
              </>
            )}
          </div>
        </div>
      </Card>

      <div className="grid cols-4">
        <div className="stat">
          <div className="stat-ico">💰</div>
          <div>
            <div className="label">Total payable</div>
            <div className="value">{money(ledger?.net_payable)}</div>
            {ledger?.discount > 0 && <div className="hint">after {money(ledger.discount)} concession</div>}
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: 'var(--green-soft)' }}>
            ✅
          </div>
          <div>
            <div className="label">Paid</div>
            <div className="value text-green">{money(ledger?.total_paid)}</div>
            <div className="hint">{ledger?.payments?.length || 0} receipt(s)</div>
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: 'var(--red-soft)' }}>
            ⏳
          </div>
          <div>
            <div className="label">Balance</div>
            <div className={`value ${ledger?.balance > 0 ? 'text-red' : 'text-green'}`}>{money(ledger?.balance)}</div>
            {ledger?.next_due && <div className="hint">next: {formatDate(ledger.next_due.due_date)}</div>}
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: '#fdeee0' }}>
            📋
          </div>
          <div>
            <div className="label">Attendance (30 days)</div>
            <div className="value">{attendance?.percentage ?? 0}%</div>
            <div className="hint">
              {attendance?.counts?.present ?? 0} present · {attendance?.counts?.absent ?? 0} absent
            </div>
          </div>
        </div>
      </div>

      <div className="row no-print">
        <div className="pill-tabs">
          {[
            ['fees', 'Fees & receipts'],
            ['profile', 'Profile'],
            ['attendance', 'Attendance'],
          ].map(([key, label]) => (
            <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'fees' && (
        <div className="stack">
          <Card
            title="Instalment schedule"
            subtitle={ledger?.academic_year ? `Academic year ${ledger.academic_year}` : undefined}
            bodyClass="tight"
            actions={
              canManage && (
                <button className="btn sm" onClick={() => setPlanning(true)}>
                  Edit fee agreement
                </button>
              )
            }
          >
            {!ledger?.installments?.length ? (
              <Empty
                icon="🧾"
                title="No fee plan yet"
                hint="Assign this child to a class that has a fee structure, then rebuild the plan."
                action={
                  canManage ? (
                    <button className="btn primary" onClick={() => setPlanning(true)}>
                      Set the agreed fee
                    </button>
                  ) : null
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Instalment</th>
                      <th>Covers</th>
                      <th>Due date</th>
                      <th className="num">Amount</th>
                      <th className="num">Paid</th>
                      <th className="num">Balance</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.installments.map((inst) => (
                      <tr key={inst.label}>
                        <td className="cell-title">{inst.label}</td>
                        <td className="cell-sub">{inst.items.map((i) => i.name).join(', ')}</td>
                        <td className="nowrap">{formatDate(inst.due_date)}</td>
                        <td className="num">{money(inst.amount)}</td>
                        <td className="num text-green">{money(inst.paid)}</td>
                        <td className="num">{money(inst.balance)}</td>
                        <td>
                          <StatusBadge status={inst.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={3} className="strong">
                        Total
                      </td>
                      <td className="num strong">{money(ledger.net_payable)}</td>
                      <td className="num strong text-green">{money(ledger.total_paid)}</td>
                      <td className="num strong text-red">{money(ledger.balance)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>

          <Card title="Payment history" bodyClass="tight">
            {!ledger?.payments?.length ? (
              <Empty icon="💳" title="No payments yet" hint="Collect the admission fee to create the first receipt." />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Receipt no.</th>
                      <th>Date</th>
                      <th>Mode</th>
                      <th>Towards</th>
                      <th className="num">Amount</th>
                      <th className="actions">Receipt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.payments.map((p) => (
                      <tr key={p.id} style={p.cancelled ? { opacity: 0.55 } : undefined}>
                        <td>
                          <Link to={`/receipts/${p.id}`}>{p.receipt_no}</Link>
                          {p.cancelled && <span className="badge red" style={{ marginLeft: 6 }}>cancelled</span>}
                        </td>
                        <td className="nowrap">{formatDate(p.paid_on)}</td>
                        <td>{modeLabel(p.mode)}</td>
                        <td className="cell-sub">{p.items?.map((i) => i.name).join(' · ') || '—'}</td>
                        <td className="num strong">{money(p.amount)}</td>
                        <td className="actions">
                          <Link className="btn sm" to={`/receipts/${p.id}`}>
                            View
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === 'profile' && (
        <div className="grid cols-2">
          <Card title="Child">
            <dl className="kv">
              <dt>Full name</dt>
              <dd>{student.full_name}</dd>
              <dt>Admission no.</dt>
              <dd>{student.admission_no}</dd>
              <dt>Date of birth</dt>
              <dd>{formatDate(student.date_of_birth)}</dd>
              <dt>Gender</dt>
              <dd>{titleCase(student.gender)}</dd>
              <dt>Class</dt>
              <dd>{student.classroom_name || '—'}</dd>
              <dt>Admitted on</dt>
              <dd>{formatDate(student.admission_date)}</dd>
              <dt>Transport</dt>
              <dd>{student.transport_opted ? student.transport_route || 'School van' : 'Own arrangement'}</dd>
              <dt>Notes</dt>
              <dd>{student.notes || '—'}</dd>
            </dl>
          </Card>

          <Card title="Parents & guardian">
            <dl className="kv">
              <dt>Father</dt>
              <dd>{g.father_name || '—'}{g.father_occupation ? ` · ${g.father_occupation}` : ''}</dd>
              <dt>Mother</dt>
              <dd>{g.mother_name || '—'}{g.mother_occupation ? ` · ${g.mother_occupation}` : ''}</dd>
              <dt>Guardian</dt>
              <dd>{g.guardian_name || '—'}</dd>
              <dt>Primary phone</dt>
              <dd>
                <a href={`tel:${g.primary_phone}`}>{g.primary_phone}</a>
              </dd>
              <dt>Alternate</dt>
              <dd>{g.alternate_phone || '—'}</dd>
              <dt>Email</dt>
              <dd>{g.email || '—'}</dd>
              <dt>Address</dt>
              <dd>{g.address || '—'}</dd>
            </dl>
          </Card>

          <Card title="Health & emergency">
            <dl className="kv">
              <dt>Blood group</dt>
              <dd>{m.blood_group || '—'}</dd>
              <dt>Allergies</dt>
              <dd className={m.allergies ? 'text-red strong' : ''}>{m.allergies || 'None recorded'}</dd>
              <dt>Conditions</dt>
              <dd>{m.conditions || '—'}</dd>
              <dt>Doctor</dt>
              <dd>{m.doctor_name || '—'}</dd>
              <dt>Doctor's phone</dt>
              <dd>{m.doctor_phone || '—'}</dd>
            </dl>
          </Card>

          <Card title="Fee structure applied">
            {!student.fee_plan?.items?.length ? (
              <p className="muted">No fee plan assigned.</p>
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>Frequency</th>
                      <th className="num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {student.fee_plan.items.map((i, idx) => (
                      <tr key={`${i.name}-${idx}`}>
                        <td>{i.name}</td>
                        <td className="muted">{titleCase(i.frequency)}</td>
                        <td className="num">{money(i.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === 'attendance' && (
        <Card
          title="Attendance — last 30 days"
          subtitle={`${attendance?.percentage ?? 0}% present across ${attendance?.working_days ?? 0} working days`}
          bodyClass="tight"
        >
          {!attendance?.records?.length ? (
            <Empty icon="📋" title="No attendance recorded" hint="Mark the roll call from the Attendance page." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Status</th>
                    <th>Remarks</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.records.map((r) => (
                    <tr key={r.date}>
                      <td className="nowrap">{formatDate(r.date)}</td>
                      <td>
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="muted">{r.remarks || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {editing && (
        <StudentForm
          student={student}
          classrooms={classrooms}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            load()
          }}
        />
      )}

      {paying && ledger && (
        <PaymentForm
          ledger={ledger}
          onClose={() => setPaying(false)}
          onPaid={(payment) => {
            setPaying(false)
            navigate(`/receipts/${payment.id}`)
          }}
        />
      )}

      {planning && (
        <FeePlanDialog
          student={student}
          ledger={ledger}
          onClose={() => setPlanning(false)}
          onSaved={() => {
            setPlanning(false)
            load()
          }}
        />
      )}
    </div>
  )
}
