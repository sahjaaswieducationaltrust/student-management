import { useCallback, useEffect, useState } from 'react'
import { useToast } from '../components/Toast'
import { Card, Confirm, Empty, Field, Loading, Modal, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDate, initials, money, toInputDate } from '../lib/format'

const blank = {
  first_name: '',
  last_name: '',
  gender: 'female',
  date_of_birth: '',
  phone: '',
  email: '',
  address: '',
  qualification: '',
  designation: 'Class Teacher',
  subjects: '',
  date_of_joining: '',
  salary: '',
  status: 'active',
  notes: '',
}

function TeacherForm({ teacher, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() =>
    teacher
      ? {
          ...blank,
          ...teacher,
          subjects: (teacher.subjects || []).join(', '),
          salary: String(teacher.salary ?? ''),
          date_of_birth: toInputDate(teacher.date_of_birth),
          date_of_joining: toInputDate(teacher.date_of_joining),
        }
      : blank,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    const payload = {
      first_name: form.first_name,
      last_name: form.last_name || null,
      gender: form.gender,
      date_of_birth: form.date_of_birth || null,
      phone: form.phone,
      email: form.email || null,
      address: form.address || null,
      qualification: form.qualification || null,
      designation: form.designation || 'Class Teacher',
      subjects: form.subjects
        ? form.subjects.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
      date_of_joining: form.date_of_joining || null,
      salary: Number(form.salary || 0),
      status: form.status,
      notes: form.notes || null,
    }
    try {
      const { data } = teacher
        ? await api.patch(`/api/teachers/${teacher.id}`, payload)
        : await api.post('/api/teachers', payload)
      toast.success(teacher ? 'Teacher updated' : `${data.full_name} added (${data.employee_no})`)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={teacher ? `Edit ${teacher.full_name}` : 'Add a teacher'}
      subtitle={teacher ? teacher.employee_no : 'An employee number is generated automatically'}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" type="submit" form="teacher-form" disabled={busy}>
            {busy ? <span className="spinner" /> : teacher ? 'Save changes' : 'Add teacher'}
          </button>
        </>
      }
    >
      <form id="teacher-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert error full">{error}</div>}
        <Field label="First name" required>
          <input required value={form.first_name} onChange={set('first_name')} />
        </Field>
        <Field label="Last name">
          <input value={form.last_name || ''} onChange={set('last_name')} />
        </Field>
        <Field label="Phone" required>
          <input required value={form.phone} onChange={set('phone')} placeholder="+91 98765 43210" />
        </Field>
        <Field label="Email">
          <input type="email" value={form.email || ''} onChange={set('email')} />
        </Field>
        <Field label="Gender">
          <select value={form.gender} onChange={set('gender')}>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </select>
        </Field>
        <Field label="Date of birth">
          <input type="date" value={form.date_of_birth || ''} onChange={set('date_of_birth')} />
        </Field>
        <Field label="Designation">
          <input value={form.designation} onChange={set('designation')} placeholder="Class Teacher" />
        </Field>
        <Field label="Qualification">
          <input value={form.qualification || ''} onChange={set('qualification')} placeholder="B.Ed, Montessori" />
        </Field>
        <Field label="Subjects / skills" hint="Comma separated" className="full">
          <input value={form.subjects} onChange={set('subjects')} placeholder="Rhymes, Art, Storytelling" />
        </Field>
        <Field label="Date of joining">
          <input type="date" value={form.date_of_joining || ''} onChange={set('date_of_joining')} />
        </Field>
        <Field label="Monthly salary">
          <input type="number" min="0" step="0.01" value={form.salary} onChange={set('salary')} />
        </Field>
        <Field label="Status">
          <select value={form.status} onChange={set('status')}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </Field>
        <Field label="Address" className="full">
          <textarea rows={2} value={form.address || ''} onChange={set('address')} />
        </Field>
        <Field label="Notes" className="full">
          <textarea rows={2} value={form.notes || ''} onChange={set('notes')} />
        </Field>
      </form>
    </Modal>
  )
}

export default function Teachers() {
  const toast = useToast()
  const { canManage, isAdmin } = useAuth()
  const [teachers, setTeachers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/api/teachers', {
        params: { search: search || undefined, status: statusFilter || undefined },
      })
      setTeachers(data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, toast])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete(`/api/teachers/${deleting.id}`)
      toast.success('Teacher removed')
      setDeleting(null)
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const payroll = teachers
    .filter((t) => t.status === 'active')
    .reduce((sum, t) => sum + Number(t.salary || 0), 0)

  return (
    <div className="stack">
      <div className="grid cols-3">
        <div className="stat">
          <div className="stat-ico">👩‍🏫</div>
          <div>
            <div className="label">Teachers listed</div>
            <div className="value">{teachers.length}</div>
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: 'var(--green-soft)' }}>
            ✅
          </div>
          <div>
            <div className="label">Active</div>
            <div className="value">{teachers.filter((t) => t.status === 'active').length}</div>
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: '#fdeee0' }}>
            💼
          </div>
          <div>
            <div className="label">Monthly payroll</div>
            <div className="value">{money(payroll, { compact: true })}</div>
          </div>
        </div>
      </div>

      <Card
        title="Teaching staff"
        bodyClass="tight"
        actions={
          canManage && (
            <button className="btn primary" onClick={() => setEditing('new')}>
              + Add teacher
            </button>
          )
        }
      >
        <div className="row" style={{ padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
          <input
            type="search"
            placeholder="Search by name, employee no. or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 320 }}
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 150 }}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="">All</option>
          </select>
        </div>

        {loading ? (
          <Loading />
        ) : teachers.length === 0 ? (
          <Empty
            icon="👩‍🏫"
            title="No teachers yet"
            hint="Add your teaching staff to assign them to classes."
            action={
              canManage ? (
                <button className="btn primary" onClick={() => setEditing('new')}>
                  + Add teacher
                </button>
              ) : null
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Teacher</th>
                  <th>Employee no.</th>
                  <th>Designation</th>
                  <th>Classes</th>
                  <th>Contact</th>
                  <th>Joined</th>
                  <th className="num">Salary</th>
                  <th>Status</th>
                  {canManage && <th className="actions">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {teachers.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        <div className="avatar" style={{ background: '#fdeee0', color: '#a25a17' }}>
                          {initials(t.full_name)}
                        </div>
                        <div>
                          <div className="cell-title">{t.full_name}</div>
                          <div className="cell-sub">{t.qualification || '—'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="muted nowrap">{t.employee_no}</td>
                    <td>{t.designation}</td>
                    <td>{t.classrooms?.length ? t.classrooms.join(', ') : <span className="muted">—</span>}</td>
                    <td>
                      <div>{t.phone}</div>
                      <div className="cell-sub">{t.email || ''}</div>
                    </td>
                    <td className="nowrap">{formatDate(t.date_of_joining)}</td>
                    <td className="num">{money(t.salary)}</td>
                    <td>
                      <StatusBadge status={t.status} />
                    </td>
                    {canManage && (
                      <td className="actions">
                        <button className="btn sm" onClick={() => setEditing(t)}>
                          Edit
                        </button>{' '}
                        {isAdmin && (
                          <button className="btn sm danger" onClick={() => setDeleting(t)}>
                            Delete
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && (
        <TeacherForm
          teacher={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}

      {deleting && (
        <Confirm
          title="Remove this teacher?"
          message={`${deleting.full_name} will be removed and unassigned from any class.`}
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
