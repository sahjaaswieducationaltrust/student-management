import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PaymentForm from '../components/PaymentForm'
import { useToast } from '../components/Toast'
import { Card, Empty, Loading, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDate, money } from '../lib/format'

export default function Fees() {
  const toast = useToast()
  const navigate = useNavigate()
  const { canManage } = useAuth()

  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [ledger, setLedger] = useState(null)
  const [loadingLedger, setLoadingLedger] = useState(false)
  const [paying, setPaying] = useState(false)

  const [dues, setDues] = useState([])
  const [classrooms, setClassrooms] = useState([])
  const [dueClass, setDueClass] = useState('')
  const [onlyOverdue, setOnlyOverdue] = useState(false)
  const [loadingDues, setLoadingDues] = useState(true)
  const ledgerRef = useRef(null)

  useEffect(() => {
    api.get('/api/classrooms').then(({ data }) => setClassrooms(data)).catch(() => {})
  }, [])

  useEffect(() => {
    const term = search.trim()
    if (term.length < 2) {
      setResults([])
      return undefined
    }
    setSearching(true)
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get('/api/students', {
          params: { search: term, page_size: 8, status: 'active' },
        })
        setResults(data.items)
      } catch (err) {
        toast.error(errorMessage(err))
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [search, toast])

  const loadDues = useCallback(async () => {
    setLoadingDues(true)
    try {
      const { data } = await api.get('/api/fees/dues', {
        params: { classroom_id: dueClass || undefined, only_overdue: onlyOverdue },
      })
      setDues(data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoadingDues(false)
    }
  }, [dueClass, onlyOverdue, toast])

  useEffect(() => {
    loadDues()
  }, [loadDues])

  /**
   * Load a child's ledger. The ledger card renders above the dues table, so
   * `collectNow` matters: clicking "Collect" from a row far down the page has
   * to open the payment dialog, otherwise the result appears off-screen and
   * the button looks dead.
   */
  const selectStudent = async (studentId, { collectNow = false } = {}) => {
    setLoadingLedger(true)
    setResults([])
    setSearch('')
    try {
      const { data } = await api.get(`/api/fees/ledger/${studentId}`)
      setLedger(data)
      if (collectNow) {
        if (data.balance > 0) {
          setPaying(true)
        } else {
          toast.info(`${data.student_name} has nothing outstanding`)
        }
      }
      ledgerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoadingLedger(false)
    }
  }

  const totalDue = dues.reduce((sum, d) => sum + d.balance, 0)
  const totalOverdue = dues.reduce((sum, d) => sum + d.overdue_amount, 0)

  return (
    <div className="stack">
      <div className="grid side">
        <Card title="Find a child" subtitle="Search by name, admission number or parent's phone">
          <input
            type="search"
            autoFocus
            placeholder="Start typing a name or admission number…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {searching && (
            <div className="row small muted" style={{ marginTop: 10 }}>
              <span className="spinner" /> Searching…
            </div>
          )}
          {results.length > 0 && (
            <div className="stack" style={{ gap: 6, marginTop: 12 }}>
              {results.map((s) => (
                <button
                  key={s.id}
                  className="btn"
                  style={{ justifyContent: 'flex-start', textAlign: 'left' }}
                  onClick={() => selectStudent(s.id)}
                >
                  <span style={{ flex: 1 }}>
                    <b>{s.full_name}</b>{' '}
                    <span className="muted small">
                      · {s.admission_no} · {s.classroom_name || 'No class'}
                    </span>
                  </span>
                  <span className="muted small">select →</span>
                </button>
              ))}
            </div>
          )}
          {search.trim().length >= 2 && !searching && results.length === 0 && (
            <p className="muted small" style={{ marginTop: 12 }}>
              No active children matched “{search}”.
            </p>
          )}
        </Card>

        <Card title="Collection today" subtitle="Quick links">
          <div className="stack" style={{ gap: 8 }}>
            <Link className="btn block" to="/receipts">
              🧾 View all receipts
            </Link>
            <Link className="btn block" to="/reports">
              📊 Collection report
            </Link>
            <Link className="btn block" to="/students">
              🧒 Children directory
            </Link>
          </div>
        </Card>
      </div>

      <div ref={ledgerRef} />

      {loadingLedger && <Loading label="Loading fee ledger…" />}

      {ledger && !loadingLedger && (
        <Card
          title={`${ledger.student_name} — fee ledger`}
          subtitle={`${ledger.admission_no} · ${ledger.classroom_name || 'No class'} · AY ${ledger.academic_year}`}
          actions={
            <div className="row">
              <Link className="btn" to={`/students/${ledger.student_id}`}>
                Open profile
              </Link>
              {canManage && (
                <button className="btn primary" onClick={() => setPaying(true)} disabled={!ledger.net_payable}>
                  💳 Collect payment
                </button>
              )}
            </div>
          }
        >
          {!ledger.net_payable ? (
            <Empty
              icon="🧾"
              title="No fee plan for this child"
              hint="Assign the child to a class with a fee structure, then rebuild the plan from their profile."
              action={
                <Link className="btn primary" to={`/students/${ledger.student_id}`}>
                  Open profile
                </Link>
              }
            />
          ) : (
            <>
              <div className="grid cols-4" style={{ marginBottom: 16 }}>
                <div className="stat">
                  <div className="stat-ico">💰</div>
                  <div>
                    <div className="label">Payable</div>
                    <div className="value">{money(ledger.net_payable)}</div>
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-ico" style={{ background: 'var(--green-soft)' }}>
                    ✅
                  </div>
                  <div>
                    <div className="label">Paid</div>
                    <div className="value text-green">{money(ledger.total_paid)}</div>
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-ico" style={{ background: 'var(--red-soft)' }}>
                    ⏳
                  </div>
                  <div>
                    <div className="label">Balance</div>
                    <div className="value text-red">{money(ledger.balance)}</div>
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-ico" style={{ background: '#fdf3dc' }}>
                    📅
                  </div>
                  <div>
                    <div className="label">Next instalment</div>
                    <div className="value">{ledger.next_due ? money(ledger.next_due.balance) : '—'}</div>
                    {ledger.next_due && <div className="hint">due {formatDate(ledger.next_due.due_date)}</div>}
                  </div>
                </div>
              </div>

              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Instalment</th>
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
                        <td>
                          <div className="cell-title">{inst.label}</div>
                          <div className="cell-sub">{inst.items.map((i) => i.name).join(', ')}</div>
                        </td>
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
                </table>
              </div>
            </>
          )}
        </Card>
      )}

      <Card
        title="Outstanding dues"
        subtitle={`${dues.length} child(ren) · ${money(totalDue)} pending · ${money(totalOverdue)} overdue`}
        bodyClass="tight"
        actions={
          <div className="row">
            <select value={dueClass} onChange={(e) => setDueClass(e.target.value)} style={{ maxWidth: 180 }}>
              <option value="">All classes</option>
              {classrooms.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <label className="check">
              <input type="checkbox" checked={onlyOverdue} onChange={(e) => setOnlyOverdue(e.target.checked)} />
              Overdue only
            </label>
          </div>
        }
      >
        {loadingDues ? (
          <Loading />
        ) : dues.length === 0 ? (
          <Empty icon="🎉" title="No pending dues" hint="Every child is up to date on fees." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Child</th>
                  <th>Class</th>
                  <th>Parent contact</th>
                  <th className="num">Payable</th>
                  <th className="num">Paid</th>
                  <th className="num">Balance</th>
                  <th className="num">Overdue</th>
                  <th>Next due</th>
                  <th className="actions" />
                </tr>
              </thead>
              <tbody>
                {dues.map((d) => (
                  <tr key={d.student_id}>
                    <td>
                      <Link className="cell-title" to={`/students/${d.student_id}`}>
                        {d.student_name}
                      </Link>
                      <div className="cell-sub">{d.admission_no}</div>
                    </td>
                    <td>{d.classroom_name || '—'}</td>
                    <td>{d.guardian_phone || '—'}</td>
                    <td className="num">{money(d.net_payable)}</td>
                    <td className="num text-green">{money(d.total_paid)}</td>
                    <td className="num strong">{money(d.balance)}</td>
                    <td className="num">
                      {d.overdue_amount > 0 ? <span className="text-red strong">{money(d.overdue_amount)}</span> : '—'}
                    </td>
                    <td className="nowrap">{formatDate(d.next_due_date)}</td>
                    <td className="actions">
                      {canManage ? (
                        <button
                          className="btn sm primary"
                          onClick={() => selectStudent(d.student_id, { collectNow: true })}
                        >
                          Collect
                        </button>
                      ) : (
                        <button className="btn sm" onClick={() => selectStudent(d.student_id)}>
                          View
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

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
    </div>
  )
}
