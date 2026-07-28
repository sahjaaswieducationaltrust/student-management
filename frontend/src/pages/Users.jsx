import { useCallback, useEffect, useState } from 'react'
import { useToast } from '../components/Toast'
import { Card, Confirm, Empty, Field, Loading, Modal, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDate, initials } from '../lib/format'

const ROLES = [
  { value: 'admin', label: 'Admin — full access, can delete and cancel receipts' },
  { value: 'staff', label: 'Staff — can manage records and collect fees' },
  { value: 'teacher', label: 'Teacher — read only, plus attendance' },
]

function UserForm({ user, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    name: user?.name || '',
    email: user?.email || '',
    role: user?.role || 'staff',
    phone: user?.phone || '',
    password: '',
    is_active: user ? user.is_active : true,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (user) {
        const payload = { name: form.name, role: form.role, phone: form.phone || null, is_active: form.is_active }
        if (form.password) payload.password = form.password
        await api.patch(`/api/users/${user.id}`, payload)
        toast.success('User updated')
      } else {
        await api.post('/api/users', {
          name: form.name,
          email: form.email,
          role: form.role,
          phone: form.phone || null,
          password: form.password,
        })
        toast.success('User created')
      }
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={user ? `Edit ${user.name}` : 'Add a user'}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" type="submit" form="user-form" disabled={busy}>
            {busy ? <span className="spinner" /> : user ? 'Save changes' : 'Create user'}
          </button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        {error && <div className="alert error">{error}</div>}
        <Field label="Full name" required>
          <input required value={form.name} onChange={set('name')} />
        </Field>
        <Field label="Email" required>
          <input type="email" required disabled={!!user} value={form.email} onChange={set('email')} />
        </Field>
        <Field label="Phone">
          <input value={form.phone} onChange={set('phone')} />
        </Field>
        <Field label="Role" required>
          <select value={form.role} onChange={set('role')}>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label={user ? 'New password' : 'Password'}
          required={!user}
          hint={user ? 'Leave blank to keep the current password' : 'At least 6 characters'}
        >
          <input
            type="password"
            required={!user}
            minLength={6}
            value={form.password}
            onChange={set('password')}
            autoComplete="new-password"
          />
        </Field>
        {user && (
          <label className="check">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Account is active
          </label>
        )}
      </form>
    </Modal>
  )
}

function ChangePasswordDialog({ onClose }) {
  const toast = useToast()
  const [form, setForm] = useState({ current_password: '', new_password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/api/auth/change-password', form)
      toast.success('Password changed')
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Change my password"
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" type="submit" form="pw-form" disabled={busy}>
            {busy ? <span className="spinner" /> : 'Change password'}
          </button>
        </>
      }
    >
      <form id="pw-form" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        {error && <div className="alert error">{error}</div>}
        <Field label="Current password" required>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={form.current_password}
            onChange={(e) => setForm({ ...form, current_password: e.target.value })}
          />
        </Field>
        <Field label="New password" required hint="At least 6 characters">
          <input
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            value={form.new_password}
            onChange={(e) => setForm({ ...form, new_password: e.target.value })}
          />
        </Field>
      </form>
    </Modal>
  )
}

export default function Users() {
  const toast = useToast()
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [changingPassword, setChangingPassword] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/api/users')
      setUsers(data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete(`/api/users/${deleting.id}`)
      toast.success('User removed')
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
        title={`User accounts (${users.length})`}
        subtitle="Who can sign in to this system"
        bodyClass="tight"
        actions={
          <div className="row">
            <button className="btn" onClick={() => setChangingPassword(true)}>
              Change my password
            </button>
            <button className="btn primary" onClick={() => setEditing('new')}>
              + Add user
            </button>
          </div>
        }
      >
        {loading ? (
          <Loading />
        ) : users.length === 0 ? (
          <Empty icon="🔐" title="No users" />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Phone</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th className="actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        <div className="avatar">{initials(u.name)}</div>
                        <div>
                          <div className="cell-title">{u.name}</div>
                          {u.id === me?.id && <div className="cell-sub">that's you</div>}
                        </div>
                      </div>
                    </td>
                    <td className="muted">{u.email}</td>
                    <td>
                      <span className={`badge ${u.role === 'admin' ? 'brand' : ''}`}>{u.role}</span>
                    </td>
                    <td>{u.phone || '—'}</td>
                    <td className="nowrap">{formatDate(u.created_at)}</td>
                    <td>
                      <StatusBadge status={u.is_active ? 'active' : 'inactive'} />
                    </td>
                    <td className="actions">
                      <button className="btn sm" onClick={() => setEditing(u)}>
                        Edit
                      </button>{' '}
                      {u.id !== me?.id && (
                        <button className="btn sm danger" onClick={() => setDeleting(u)}>
                          Delete
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

      {editing && (
        <UserForm
          user={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}

      {changingPassword && <ChangePasswordDialog onClose={() => setChangingPassword(false)} />}

      {deleting && (
        <Confirm
          title="Delete this user?"
          message={`${deleting.name} (${deleting.email}) will no longer be able to sign in.`}
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
