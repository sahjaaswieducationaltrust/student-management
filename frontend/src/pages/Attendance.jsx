import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { Card, ChildAvatar, Empty, Loading } from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { today } from '../lib/format'

const OPTIONS = [
  { value: 'present', label: 'Present', tone: 'green' },
  { value: 'absent', label: 'Absent', tone: 'red' },
  { value: 'late', label: 'Late', tone: 'amber' },
  { value: 'holiday', label: 'Holiday', tone: '' },
]

export default function Attendance() {
  const toast = useToast()
  const [classrooms, setClassrooms] = useState([])
  const [classroomId, setClassroomId] = useState('')
  // Daycare cuts across classes, so its roll is drawn from who is enrolled in
  // daycare rather than from a class.
  const [session, setSession] = useState('class')
  const [date, setDate] = useState(today())
  const [rows, setRows] = useState([])
  const [marks, setMarks] = useState({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .get('/api/classrooms')
      .then(({ data }) => {
        setClassrooms(data)
        if (data.length) setClassroomId((current) => current || data[0].id)
      })
      .catch((err) => toast.error(errorMessage(err)))
  }, [toast])

  const load = useCallback(async () => {
    if (session === 'class' && !classroomId) return
    setLoading(true)
    try {
      const { data } = await api.get('/api/attendance', {
        params: {
          // The daycare roll spans every class, so no class is sent for it.
          classroom_id: session === 'class' ? classroomId : undefined,
          session,
          date,
        },
      })
      setRows(data)
      setMarks(Object.fromEntries(data.map((r) => [r.student_id, r.status || 'present'])))
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [classroomId, session, date, toast])

  useEffect(() => {
    load()
  }, [load])

  const setAll = (status) => setMarks(Object.fromEntries(rows.map((r) => [r.student_id, status])))

  const save = async () => {
    setSaving(true)
    try {
      await api.post('/api/attendance', {
        classroom_id: session === 'class' ? classroomId : null,
        session,
        date,
        entries: rows.map((r) => ({ student_id: r.student_id, status: marks[r.student_id] || 'present' })),
      })
      toast.success('Attendance saved')
      load()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const counts = OPTIONS.reduce(
    (acc, o) => ({ ...acc, [o.value]: Object.values(marks).filter((m) => m === o.value).length }),
    {},
  )
  const alreadySaved = rows.some((r) => r.status)

  return (
    <div className="stack">
      <Card
        title="Daily roll call"
        subtitle={alreadySaved ? 'Attendance for this day is already recorded — you can update it' : 'Mark each child and save'}
        actions={
          <button className="btn primary" onClick={save} disabled={saving || rows.length === 0}>
            {saving ? <span className="spinner" /> : alreadySaved ? 'Update attendance' : 'Save attendance'}
          </button>
        }
      >
        <div className="row">
          <div className="field" style={{ minWidth: 180 }}>
            <label>Session</label>
            <select value={session} onChange={(e) => setSession(e.target.value)}>
              <option value="class">Class roll call</option>
              <option value="daycare">Daycare</option>
            </select>
          </div>
          {session === 'class' && (
            <div className="field" style={{ minWidth: 200 }}>
              <label>Class</label>
              <select value={classroomId} onChange={(e) => setClassroomId(e.target.value)}>
                {classrooms.length === 0 && <option value="">No classes</option>}
                {classrooms.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.student_count})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field" style={{ minWidth: 170 }}>
            <label>Date</label>
            <input type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="spacer" />
          {rows.length > 0 && (
            <div className="row" style={{ alignSelf: 'flex-end' }}>
              <span className="small muted">Mark all:</span>
              {OPTIONS.map((o) => (
                <button key={o.value} className="btn sm" onClick={() => setAll(o.value)}>
                  {o.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {rows.length > 0 && (
          <div className="row" style={{ marginTop: 14, gap: 8 }}>
            {OPTIONS.map((o) => (
              <span key={o.value} className={`badge ${o.tone}`}>
                {o.label}: {counts[o.value] || 0}
              </span>
            ))}
            <span className="badge brand">Total: {rows.length}</span>
          </div>
        )}
      </Card>

      <Card bodyClass="tight">
        {loading ? (
          <Loading />
        ) : rows.length === 0 ? (
          <Empty
            icon="📋"
            title={
              session === 'daycare'
                ? 'Nobody is enrolled in daycare'
                : classrooms.length
                  ? 'No active children in this class'
                  : 'Create a class first'
            }
            hint={
              session === 'daycare'
                ? "Tick 'Stays for daycare' on a child's profile and set their hours."
                : classrooms.length
                  ? 'Enrol children into this class to take attendance.'
                  : undefined
            }
            action={
              <Link className="btn primary" to={classrooms.length ? '/students' : '/classes'}>
                {classrooms.length ? 'Go to Children' : 'Go to Classes'}
              </Link>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th style={{ width: 50 }}>#</th>
                  <th>Child</th>
                  <th>Admission no.</th>
                  <th style={{ width: 340 }}>Attendance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, index) => (
                  <tr key={r.student_id}>
                    <td className="muted">{index + 1}</td>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        <ChildAvatar gender={r.gender} name={r.student_name} />
                        <div style={{ minWidth: 0 }}>
                          <Link to={`/students/${r.student_id}`} className="cell-title">
                            {r.student_name}
                          </Link>
                          {session === 'daycare' && r.daycare_hours != null && (
                            <div className="cell-sub">{r.daycare_hours} hrs/day</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="muted">{r.admission_no}</td>
                    <td>
                      <div className="pill-tabs" style={{ display: 'inline-flex' }}>
                        {OPTIONS.map((o) => (
                          <button
                            key={o.value}
                            className={marks[r.student_id] === o.value ? 'active' : ''}
                            onClick={() => setMarks((m) => ({ ...m, [r.student_id]: o.value }))}
                          >
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
