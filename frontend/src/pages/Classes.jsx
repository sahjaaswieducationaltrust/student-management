import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { Card, Confirm, Empty, Field, Loading, Modal } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { FREQUENCIES, OCCURRENCES, annualTotal, money, titleCase } from '../lib/format'

const LEVELS = ['Daycare', 'Playgroup', 'Nursery', 'LKG', 'UKG']

function ClassForm({ classroom, teachers, academicYear, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(() => ({
    name: classroom?.name || '',
    level: classroom?.level || 'Nursery',
    room: classroom?.room || '',
    capacity: String(classroom?.capacity ?? 20),
    academic_year: classroom?.academic_year || academicYear || '',
    class_teacher_id: classroom?.class_teacher_id || '',
    fee_components: classroom?.fee_components?.length
      ? classroom.fee_components.map((c) => ({ ...c, amount: String(c.amount) }))
      : [{ name: 'Admission Fee', amount: '', frequency: 'one_time' }],
  }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const setComponent = (index, key, value) =>
    setForm((f) => ({
      ...f,
      fee_components: f.fee_components.map((c, i) => (i === index ? { ...c, [key]: value } : c)),
    }))

  const addComponent = () =>
    setForm((f) => ({
      ...f,
      fee_components: [...f.fee_components, { name: '', amount: '', frequency: 'monthly' }],
    }))

  const removeComponent = (index) =>
    setForm((f) => ({ ...f, fee_components: f.fee_components.filter((_, i) => i !== index) }))

  const components = form.fee_components
    .filter((c) => c.name.trim() && Number(c.amount) > 0)
    .map((c) => ({ name: c.name.trim(), amount: Number(c.amount), frequency: c.frequency }))

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    const payload = {
      name: form.name.trim(),
      level: form.level,
      room: form.room || null,
      capacity: Number(form.capacity || 20),
      academic_year: form.academic_year || null,
      class_teacher_id: form.class_teacher_id || null,
      fee_components: components,
    }
    try {
      if (classroom) await api.patch(`/api/classrooms/${classroom.id}`, payload)
      else await api.post('/api/classrooms', payload)
      toast.success(classroom ? 'Class updated' : 'Class created')
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={classroom ? `Edit ${classroom.name}` : 'Create a class'}
      subtitle="The fee structure here becomes each child's instalment schedule"
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn primary" type="submit" form="class-form" disabled={busy}>
            {busy ? <span className="spinner" /> : classroom ? 'Save changes' : 'Create class'}
          </button>
        </>
      }
    >
      <form id="class-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert error full">{error}</div>}
        <Field label="Class name" required>
          <input required value={form.name} onChange={set('name')} placeholder="Nursery A" />
        </Field>
        <Field label="Level">
          <select value={form.level} onChange={set('level')}>
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Room">
          <input value={form.room} onChange={set('room')} placeholder="Rainbow Room" />
        </Field>
        <Field label="Capacity">
          <input type="number" min="1" max="200" value={form.capacity} onChange={set('capacity')} />
        </Field>
        <Field label="Class teacher">
          <select value={form.class_teacher_id} onChange={set('class_teacher_id')}>
            <option value="">— Not assigned —</option>
            {teachers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Academic year">
          <input value={form.academic_year} onChange={set('academic_year')} placeholder="2026-27" />
        </Field>

        <div className="section-label">Fee structure</div>
        <div className="full stack" style={{ gap: 10 }}>
          {form.fee_components.map((c, index) => (
            <div className="row" key={index} style={{ gap: 8, flexWrap: 'nowrap' }}>
              <input
                placeholder="Component (e.g. Tuition Fee)"
                value={c.name}
                onChange={(e) => setComponent(index, 'name', e.target.value)}
                style={{ flex: 2 }}
              />
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="Amount"
                value={c.amount}
                onChange={(e) => setComponent(index, 'amount', e.target.value)}
                style={{ flex: 1, minWidth: 100 }}
              />
              <select
                value={c.frequency}
                onChange={(e) => setComponent(index, 'frequency', e.target.value)}
                style={{ flex: 1.3, minWidth: 150 }}
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn sm danger"
                onClick={() => removeComponent(index)}
                disabled={form.fee_components.length === 1}
                title="Remove"
              >
                ✕
              </button>
            </div>
          ))}
          <div className="row">
            <button type="button" className="btn sm" onClick={addComponent}>
              + Add component
            </button>
            <div className="spacer" />
            <span className="muted small">Annual total per child</span>
            <b>{money(annualTotal(components))}</b>
          </div>
          <p className="help">
            A monthly component is charged 12 times a year, quarterly 4 times, per-term 3 times.
            One-time components are billed with the first instalment.
          </p>
        </div>
      </form>
    </Modal>
  )
}

export default function Classes() {
  const toast = useToast()
  const { canManage } = useAuth()
  const [classrooms, setClassrooms] = useState([])
  const [teachers, setTeachers] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [c, t] = await Promise.all([
        api.get('/api/classrooms'),
        api.get('/api/teachers', { params: { status: 'active' } }),
      ])
      setClassrooms(c.data)
      setTeachers(t.data)
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
      await api.delete(`/api/classrooms/${deleting.id}`)
      toast.success('Class deleted')
      setDeleting(null)
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <Loading />

  return (
    <div className="stack">
      <Card
        title={`Classes (${classrooms.length})`}
        subtitle="Each class carries its own fee structure"
        bodyClass="tight"
        actions={
          canManage && (
            <button className="btn primary" onClick={() => setEditing('new')}>
              + Create class
            </button>
          )
        }
      >
        {classrooms.length === 0 ? (
          <Empty
            icon="🏫"
            title="No classes yet"
            hint="Create Playgroup, Nursery, LKG and UKG with their fee structures."
            action={
              canManage ? (
                <button className="btn primary" onClick={() => setEditing('new')}>
                  + Create class
                </button>
              ) : null
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Class</th>
                  <th>Level</th>
                  <th>Class teacher</th>
                  <th>Room</th>
                  <th className="num">Children</th>
                  <th className="num">Annual fee</th>
                  <th className="actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {classrooms.map((c) => (
                  <Fragment key={c.id}>
                    <tr>
                      <td>
                        <div className="cell-title">{c.name}</div>
                        <div className="cell-sub">AY {c.academic_year || '—'}</div>
                      </td>
                      <td>
                        <span className="badge brand">{c.level}</span>
                      </td>
                      <td>{c.class_teacher_name || <span className="muted">Not assigned</span>}</td>
                      <td>{c.room || '—'}</td>
                      <td className="num">
                        {c.student_count} <span className="muted">/ {c.capacity}</span>
                      </td>
                      <td className="num strong">{money(c.annual_fee)}</td>
                      <td className="actions">
                        <button className="btn sm" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                          {expanded === c.id ? 'Hide fees' : 'Fees'}
                        </button>{' '}
                        <Link className="btn sm" to={`/students?class=${c.id}`}>
                          Children
                        </Link>{' '}
                        {canManage && (
                          <>
                            <button className="btn sm" onClick={() => setEditing(c)}>
                              Edit
                            </button>{' '}
                            <button className="btn sm danger" onClick={() => setDeleting(c)}>
                              Delete
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                    {expanded === c.id && (
                      <tr>
                        <td colSpan={7} style={{ background: '#fafbfd' }}>
                          {!c.fee_components?.length ? (
                            <p className="muted small">
                              No fee structure defined for this class yet — edit the class to add one.
                            </p>
                          ) : (
                            <table className="data" style={{ background: 'transparent' }}>
                              <thead>
                                <tr>
                                  <th>Component</th>
                                  <th>Frequency</th>
                                  <th className="num">Per instalment</th>
                                  <th className="num">Times a year</th>
                                  <th className="num">Annual</th>
                                </tr>
                              </thead>
                              <tbody>
                                {c.fee_components.map((f, i) => (
                                  <tr key={`${f.name}-${i}`}>
                                    <td>{f.name}</td>
                                    <td className="muted">{titleCase(f.frequency)}</td>
                                    <td className="num">{money(f.amount)}</td>
                                    <td className="num">{OCCURRENCES[f.frequency] || 1}</td>
                                    <td className="num strong">
                                      {money(Number(f.amount) * (OCCURRENCES[f.frequency] || 1))}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && (
        <ClassForm
          classroom={editing === 'new' ? null : editing}
          teachers={teachers}
          academicYear={classrooms[0]?.academic_year}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}

      {deleting && (
        <Confirm
          title="Delete this class?"
          message={`${deleting.name} will be deleted. Classes with children assigned cannot be deleted.`}
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
