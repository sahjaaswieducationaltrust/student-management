import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import StudentForm from '../components/StudentForm'
import { useToast } from '../components/Toast'
import { Card, ChildAvatar, Confirm, Empty, Loading, Pagination, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { feeCategoryLabel, formatDate, isFreeCategory, money } from '../lib/format'

const PAGE_SIZE = 15

export default function Students() {
  const toast = useToast()
  const { canManage, isAdmin } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [data, setData] = useState({ items: [], total: 0, totals: null })
  const [classrooms, setClassrooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [classFilter, setClassFilter] = useState(() => searchParams.get('class') || '')
  const [statusFilter, setStatusFilter] = useState('active')
  const [duesFilter, setDuesFilter] = useState('')
  const [editing, setEditing] = useState(null) // null | 'new' | student
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data: res } = await api.get('/api/students', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: debounced || undefined,
          classroom_id: classFilter || undefined,
          status: statusFilter || undefined,
          dues: duesFilter || undefined,
        },
      })
      setData(res)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [page, debounced, classFilter, statusFilter, duesFilter, toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.get('/api/classrooms').then(({ data: res }) => setClassrooms(res)).catch(() => {})
  }, [])

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete(`/api/students/${deleting.id}`)
      toast.success(`${deleting.full_name} removed`)
      setDeleting(null)
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <Card
        bodyClass="tight"
        title={`Children (${data.total})`}
        subtitle="Enrolment records, guardians and fee plans"
        actions={
          canManage && (
            <button className="btn primary" onClick={() => setEditing('new')}>
              + Enrol child
            </button>
          )
        }
      >
        <div className="row" style={{ padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
          <input
            type="search"
            placeholder="Search by name, admission no. or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 320 }}
          />
          <select
            value={classFilter}
            onChange={(e) => {
              setClassFilter(e.target.value)
              setPage(1)
              setSearchParams(e.target.value ? { class: e.target.value } : {}, { replace: true })
            }}
            style={{ maxWidth: 190 }}
          >
            <option value="">All classes</option>
            {classrooms.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            style={{ maxWidth: 150 }}
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="graduated">Graduated</option>
            <option value="">All statuses</option>
          </select>
          <select
            value={duesFilter}
            onChange={(e) => {
              setDuesFilter(e.target.value)
              setPage(1)
            }}
            style={{ maxWidth: 170 }}
            title="Filter by fee position"
          >
            <option value="">All fee positions</option>
            <option value="pending">Has pending dues</option>
            <option value="overdue">Overdue only</option>
            <option value="clear">Fully paid</option>
          </select>
        </div>

        {data.totals && data.total > 0 && (
          <div className="fee-totals-bar">
            <div>
              <span>Total fee ({data.total} children)</span>
              <b>{money(data.totals.net_payable)}</b>
            </div>
            <div>
              <span>Collected</span>
              <b className="text-green">{money(data.totals.total_paid)}</b>
            </div>
            <div>
              <span>Pending due</span>
              <b className={data.totals.balance > 0 ? 'text-red' : 'text-green'}>
                {money(data.totals.balance)}
              </b>
            </div>
            <div>
              <span>Overdue</span>
              <b className={data.totals.overdue_amount > 0 ? 'text-red' : ''}>
                {money(data.totals.overdue_amount)}
              </b>
            </div>
          </div>
        )}

        {loading ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <Empty
            icon="🧒"
            title="No children found"
            hint={debounced ? 'Try a different search term.' : 'Enrol your first child to get started.'}
            action={
              canManage && !debounced ? (
                <button className="btn primary" onClick={() => setEditing('new')}>
                  + Enrol child
                </button>
              ) : null
            }
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Child</th>
                    <th>Admission no.</th>
                    <th>Class</th>
                    <th>Guardian contact</th>
                    <th className="num">Total fee</th>
                    <th className="num">Paid</th>
                    <th className="num">Balance</th>
                    <th>Next due</th>
                    <th>Status</th>
                    <th className="actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                          <ChildAvatar gender={s.gender} name={s.full_name} />
                          <div style={{ minWidth: 0 }}>
                            <Link to={`/students/${s.id}`} className="cell-title">
                              {s.full_name}
                            </Link>
                            <div className="cell-sub">
                              {s.gender === 'female' ? 'Girl' : s.gender === 'male' ? 'Boy' : 'Child'}
                              {s.medical?.allergies ? ` · ⚠ ${s.medical.allergies}` : ''}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="muted nowrap">{s.admission_no}</td>
                      <td>{s.classroom_name || <span className="muted">—</span>}</td>
                      <td>
                        <div>{s.guardian?.primary_phone}</div>
                        <div className="cell-sub">{s.guardian?.father_name || s.guardian?.mother_name || ''}</div>
                      </td>
                      <td className="num">
                        {isFreeCategory(s.fee_category) ? (
                          <>
                            <span className="badge green">free</span>
                            <div className="cell-sub">{feeCategoryLabel(s.fee_category)}</div>
                          </>
                        ) : s.fee_summary?.net_payable ? (
                          money(s.fee_summary.net_payable)
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="num text-green">{money(s.fee_summary?.total_paid)}</td>
                      <td className="num strong">
                        {s.fee_summary?.balance > 0 ? (
                          <span className={s.fee_summary.overdue_amount > 0 ? 'text-red' : ''}>
                            {money(s.fee_summary.balance)}
                          </span>
                        ) : (
                          <span className="badge green">clear</span>
                        )}
                      </td>
                      <td className="nowrap">
                        {s.fee_summary?.next_due_date ? (
                          <>
                            <div>{formatDate(s.fee_summary.next_due_date)}</div>
                            <div className="cell-sub">{money(s.fee_summary.next_due_amount)}</div>
                          </>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <StatusBadge status={s.status} />
                      </td>
                      <td className="actions">
                        <Link className="btn sm" to={`/students/${s.id}`}>
                          View
                        </Link>{' '}
                        {canManage && (
                          <button className="btn sm" onClick={() => setEditing(s)}>
                            Edit
                          </button>
                        )}{' '}
                        {isAdmin && (
                          <button className="btn sm danger" onClick={() => setDeleting(s)}>
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
          </>
        )}
      </Card>

      {editing && (
        <StudentForm
          student={editing === 'new' ? null : editing}
          classrooms={classrooms}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}

      {deleting && (
        <Confirm
          title="Delete this child's record?"
          message={`${deleting.full_name} (${deleting.admission_no}) will be permanently removed along with attendance history. Children with receipts cannot be deleted — mark them inactive instead.`}
          confirmLabel="Delete"
          danger
          busy={busy}
          onConfirm={remove}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  )
}
