import { useCallback, useEffect, useState } from 'react'
import { useToast } from '../components/Toast'
import { Card, Confirm, Empty, Field, Loading, Modal, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDate, initials, money, toInputDate } from '../lib/format'

// Suggestions only — the field stays free text, since every branch names these
// roles a little differently (ayah / aaya / helper / caretaker).
const DEPARTMENTS = [
  'Front Office',
  'Administration',
  'Accounts',
  'Care',
  'Housekeeping',
  'Kitchen',
  'Transport',
  'Security',
  'Maintenance',
  'Nursing',
]

const DESIGNATIONS = [
  'Receptionist',
  'Office Assistant',
  'Accountant',
  'Ayah / Helper',
  'Caretaker',
  'Housekeeping Attendant',
  'Cook',
  'Kitchen Helper',
  'Van Driver',
  'Van Attendant',
  'Security Guard',
  'Gardener',
  'Maintenance Technician',
  'Nurse',
]

const blank = {
  first_name: '',
  last_name: '',
  gender: 'female',
  date_of_birth: '',
  phone: '',
  email: '',
  address: '',
  qualification: '',
  department: 'Front Office',
  designation: 'Support Staff',
  duties: '',
  date_of_joining: '',
  salary: '',
  emergency_contact: '',
  status: 'active',
  notes: '',
}

function StaffForm({ member, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() =>
    member
      ? {
          ...blank,
          ...member,
          duties: (member.duties || []).join(', '),
          salary: String(member.salary ?? ''),
          date_of_birth: toInputDate(member.date_of_birth),
          date_of_joining: toInputDate(member.date_of_joining),
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
      department: form.department || 'Support',
      designation: form.designation || 'Support Staff',
      duties: form.duties
        ? form.duties.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
      date_of_joining: form.date_of_joining || null,
      salary: Number(form.salary || 0),
      emergency_contact: form.emergency_contact || null,
      status: form.status,
      notes: form.notes || null,
    }
    try {
      const { data } = member
        ? await api.patch(`/api/staff/${member.id}`, payload)
        : await api.post('/api/staff', payload)
      toast.success(member ? 'Staff member updated' : `${data.full_name} added (${data.employee_no})`)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={member ? `Edit ${member.full_name}` : 'Add a staff member'}
      subtitle={member ? member.employee_no : 'An employee number is generated automatically'}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" type="submit" form="staff-form" disabled={busy}>
            {busy ? <span className="spinner" /> : member ? 'Save changes' : 'Add staff member'}
          </button>
        </>
      }
    >
      <form id="staff-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert error full">{error}</div>}
        <datalist id="staff-departments">
          {DEPARTMENTS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
        <datalist id="staff-designations">
          {DESIGNATIONS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
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
        <Field label="Department">
          <input
            list="staff-departments"
            value={form.department}
            onChange={set('department')}
            placeholder="Front Office"
          />
        </Field>
        <Field label="Designation">
          <input
            list="staff-designations"
            value={form.designation}
            onChange={set('designation')}
            placeholder="Receptionist"
          />
        </Field>
        <Field label="Qualification">
          <input value={form.qualification || ''} onChange={set('qualification')} placeholder="B.Com" />
        </Field>
        <Field label="Emergency contact">
          <input
            value={form.emergency_contact || ''}
            onChange={set('emergency_contact')}
            placeholder="+91 98765 43210"
          />
        </Field>
        <Field label="Duties" hint="Comma separated" className="full">
          <input value={form.duties} onChange={set('duties')} placeholder="Gate duty, Visitor register" />
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

export default function Staff() {
  const toast = useToast()
  const { canManage, isAdmin } = useAuth()
  const [members, setMembers] = useState([])
  const [departments, setDepartments] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/api/staff', {
        params: {
          search: search || undefined,
          status: statusFilter || undefined,
          department: departmentFilter || undefined,
        },
      })
      setMembers(data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, departmentFilter, toast])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  // Kept out of `load` so the filter never loses the department you are
  // standing on just because the current filter returns nothing.
  const loadDepartments = useCallback(async () => {
    try {
      const { data } = await api.get('/api/staff/departments')
      setDepartments(data)
    } catch {
      /* the filter simply stays on "All departments" */
    }
  }, [])

  useEffect(() => {
    loadDepartments()
  }, [loadDepartments])

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete(`/api/staff/${deleting.id}`)
      toast.success('Staff member removed')
      setDeleting(null)
      load()
      loadDepartments()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const active = members.filter((m) => m.status === 'active')
  const payroll = active.reduce((sum, m) => sum + Number(m.salary || 0), 0)
  const departmentCount = new Set(active.map((m) => m.department).filter(Boolean)).size

  return (
    <div className="stack">
      <div className="grid cols-4">
        <div className="stat">
          <div className="stat-ico">🧹</div>
          <div>
            <div className="label">Staff listed</div>
            <div className="value">{members.length}</div>
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: 'var(--green-soft)' }}>
            ✅
          </div>
          <div>
            <div className="label">Active</div>
            <div className="value">{active.length}</div>
          </div>
        </div>
        <div className="stat">
          <div className="stat-ico" style={{ background: '#e8eefb' }}>
            🏷️
          </div>
          <div>
            <div className="label">Departments</div>
            <div className="value">{departmentCount}</div>
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
        title="Non-teaching staff"
        subtitle="Front office, care, kitchen, housekeeping, transport and security"
        bodyClass="tight"
        actions={
          canManage && (
            <button className="btn primary" onClick={() => setEditing('new')}>
              + Add staff member
            </button>
          )
        }
      >
        <div className="row" style={{ padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
          <input
            type="search"
            placeholder="Search by name, employee no., role or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 320 }}
          />
          <select
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value)}
            style={{ maxWidth: 190 }}
          >
            <option value="">All departments</option>
            {departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ maxWidth: 150 }}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="">All</option>
          </select>
        </div>

        {loading ? (
          <Loading />
        ) : members.length === 0 ? (
          <Empty
            icon="🧹"
            title="No non-teaching staff yet"
            hint="Add the front office, helpers, kitchen, drivers and security here."
            action={
              canManage ? (
                <button className="btn primary" onClick={() => setEditing('new')}>
                  + Add staff member
                </button>
              ) : null
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Staff member</th>
                  <th>Employee no.</th>
                  <th>Department</th>
                  <th>Designation</th>
                  <th>Duties</th>
                  <th>Contact</th>
                  <th>Joined</th>
                  <th className="num">Salary</th>
                  <th>Status</th>
                  {canManage && <th className="actions">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        <div className="avatar" style={{ background: '#e8eefb', color: '#2f4d8a' }}>
                          {initials(m.full_name)}
                        </div>
                        <div>
                          <div className="cell-title">{m.full_name}</div>
                          <div className="cell-sub">{m.qualification || '—'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="muted nowrap">{m.employee_no}</td>
                    <td>{m.department}</td>
                    <td>{m.designation}</td>
                    <td>{m.duties?.length ? m.duties.join(', ') : <span className="muted">—</span>}</td>
                    <td>
                      <div>{m.phone}</div>
                      <div className="cell-sub">{m.email || ''}</div>
                    </td>
                    <td className="nowrap">{formatDate(m.date_of_joining)}</td>
                    <td className="num">{money(m.salary)}</td>
                    <td>
                      <StatusBadge status={m.status} />
                    </td>
                    {canManage && (
                      <td className="actions">
                        <button className="btn sm" onClick={() => setEditing(m)}>
                          Edit
                        </button>{' '}
                        {isAdmin && (
                          <button className="btn sm danger" onClick={() => setDeleting(m)}>
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
        <StaffForm
          member={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
            loadDepartments()
          }}
        />
      )}

      {deleting && (
        <Confirm
          title="Remove this staff member?"
          message={`${deleting.full_name} will be removed from the staff register.`}
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
