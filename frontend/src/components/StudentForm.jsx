import { useEffect, useMemo, useState } from 'react'
import api, { errorMessage } from '../lib/api'
import {
  CUSTOM_PARTICULARS,
  FEE_CATEGORIES,
  FEE_PARTICULARS,
  PAYMENT_MODES,
  annualTotal,
  isFreeCategory,
  money,
  titleCase,
  toInputDate,
  today,
} from '../lib/format'
import { useAuth } from '../context/AuthContext'
import { Field, Modal } from './ui'
import { useToast } from './Toast'

const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

const blank = {
  first_name: '',
  last_name: '',
  gender: 'male',
  date_of_birth: '',
  classroom_id: '',
  admission_date: today(),
  status: 'active',
  guardian: {
    father_name: '',
    father_occupation: '',
    mother_name: '',
    mother_occupation: '',
    guardian_name: '',
    relation: 'Parent',
    primary_phone: '',
    alternate_phone: '',
    email: '',
    address: '',
  },
  medical: { blood_group: '', allergies: '', conditions: '', doctor_name: '', doctor_phone: '' },
  transport_opted: false,
  transport_route: '',
  notes: '',
  fee_category: 'regular',
  // daycare add-on — independent of the class the child is in
  daycare_enrolled: false,
  daycare_hours: '',
  daycare_rate: '',
  daycare_note: '',
  // fee agreement (new enrolments only)
  agreed_fee: '',
  fee_note: '',
  collect_initial: false,
  initial_amount: '',
  initial_mode: 'cash',
  initial_reference: '',
  initial_date: today(),
  initial_particulars: 'Admission Fee',
}

function fromStudent(student) {
  if (!student) return blank
  return {
    ...blank,
    ...student,
    date_of_birth: toInputDate(student.date_of_birth),
    admission_date: toInputDate(student.admission_date),
    classroom_id: student.classroom_id || '',
    guardian: { ...blank.guardian, ...(student.guardian || {}) },
    medical: { ...blank.medical, ...(student.medical || {}) },
    daycare_enrolled: !!student.daycare?.enrolled,
    daycare_hours: student.daycare?.hours_per_day ? String(student.daycare.hours_per_day) : '',
    daycare_rate: student.daycare?.rate_per_hour ? String(student.daycare.rate_per_hour) : '',
    daycare_note: student.daycare?.note || '',
  }
}

/** Strip empty strings so the API sees `null` instead of "". */
function clean(value) {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clean(v)]))
  }
  return value === '' ? null : value
}

export default function StudentForm({ student, classrooms, onClose, onSaved }) {
  const toast = useToast()
  const { school } = useAuth()
  const [form, setForm] = useState(() => fromStudent(student))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const setNested = (group, key) => (e) =>
    setForm((f) => ({ ...f, [group]: { ...f[group], [key]: e.target.value } }))

  // ---- fee agreement (new enrolments only) ----
  const selectedClass = useMemo(
    () => classrooms.find((c) => c.id === form.classroom_id) || null,
    [classrooms, form.classroom_id],
  )
  const components = selectedClass?.fee_components || []
  const standardFee = useMemo(() => annualTotal(components), [components])
  const freeSeat = isFreeCategory(form.fee_category)

  // Picking a class loads that class's standard fee into the agreed-fee box,
  // which the admin then overrides with whatever was settled with the parents.
  // A concession category is a full waiver, so it pins the box to zero instead.
  useEffect(() => {
    if (student) return // editing: never touch an existing fee plan
    setForm((f) => ({
      ...f,
      agreed_fee: freeSeat ? '0' : standardFee ? String(standardFee) : '',
      collect_initial: freeSeat ? false : f.collect_initial,
    }))
  }, [standardFee, student, freeSeat])

  // Daycare is priced per hour of daily stay, per month, at a rate that
  // depends on the child's age. Mirrors services/daycare.py so the desk sees
  // the same number the server will charge.
  const ageYears = useMemo(() => {
    if (!form.date_of_birth) return null
    const dob = new Date(form.date_of_birth)
    if (Number.isNaN(dob.getTime())) return null
    return (Date.now() - dob.getTime()) / (365.25 * 24 * 3600 * 1000)
  }, [form.date_of_birth])

  const suggestedRate =
    ageYears == null || ageYears < (school.daycare_age_threshold ?? 3)
      ? school.daycare_rate_under ?? 1000
      : school.daycare_rate_over ?? 700

  const daycareRate = form.daycare_rate === '' ? suggestedRate : Number(form.daycare_rate)
  const daycareHours = Number(form.daycare_hours || 0)
  const daycareMonthly = form.daycare_enrolled ? daycareHours * daycareRate : 0

  const agreedFee = Number(form.agreed_fee || 0)
  const difference = agreedFee - standardFee
  const initialAmount = Number(form.initial_amount || 0)
  const balanceAfter = agreedFee - (form.collect_initial ? initialAmount : 0)

  const submit = async (event) => {
    event.preventDefault()

    if (!student && form.collect_initial) {
      if (initialAmount <= 0) {
        setError('Enter the first instalment amount, or untick "Collect first instalment now".')
        return
      }
      if (agreedFee > 0 && initialAmount > agreedFee) {
        setError(
          `First instalment (${money(initialAmount)}) is more than the total agreed fee (${money(agreedFee)}).`,
        )
        return
      }
    }

    setBusy(true)
    setError('')
    const payload = clean({
      ...form,
      classroom_id: form.classroom_id || null,
      transport_route: form.transport_opted ? form.transport_route : null,
    })
    for (const key of [
      'id', 'admission_no', 'full_name', 'age', 'classroom_name', 'created_at',
      'fee_plan', 'fee_summary', 'fee_category_label', 'next_due_override',
      'initial_receipt',
      'agreed_fee', 'fee_note', 'collect_initial', 'initial_amount',
      'initial_mode', 'initial_reference', 'initial_date', 'initial_particulars',
      'daycare_enrolled', 'daycare_hours', 'daycare_rate', 'daycare_note',
      'daycare_note_text',
    ]) {
      delete payload[key]
    }
    payload.transport_opted = !!form.transport_opted
    // The server re-derives the rate and the monthly fee; sending them keeps
    // an agreed rate from being reset when someone edits an older record.
    payload.daycare = form.daycare_enrolled
      ? {
          enrolled: true,
          hours_per_day: daycareHours,
          rate_per_hour: daycareRate,
          note: form.daycare_note || null,
        }
      : { enrolled: false, hours_per_day: 0 }

    if (!student) {
      if (form.agreed_fee !== '') payload.agreed_fee = agreedFee
      if (form.fee_note) payload.fee_note = form.fee_note
      if (form.collect_initial && initialAmount > 0) {
        payload.initial_payment = {
          amount: initialAmount,
          mode: form.initial_mode,
          paid_on: form.initial_date || null,
          reference: form.initial_reference || null,
          remarks: 'Initial admission payment',
          particulars: form.initial_particulars || null,
        }
      }
    }

    try {
      const { data } = student
        ? await api.patch(`/api/students/${student.id}`, payload)
        : await api.post('/api/students', payload)
      toast.success(
        student
          ? 'Child profile updated'
          : data.initial_receipt
            ? `Enrolled ${data.full_name} · receipt ${data.initial_receipt.receipt_no}`
            : `Enrolled ${data.full_name} (${data.admission_no})`,
      )
      onSaved(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={student ? `Edit ${student.full_name}` : 'Enrol a new child'}
      subtitle={student ? student.admission_no : 'An admission number is generated automatically'}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" form="student-form" className="btn primary" disabled={busy}>
            {busy ? <span className="spinner" /> : student ? 'Save changes' : 'Enrol child'}
          </button>
        </>
      }
    >
      <form id="student-form" onSubmit={submit} className="form-grid">
        {error && <div className="alert error full">{error}</div>}

        <div className="section-label">Child details</div>
        <Field label="First name" required>
          <input required value={form.first_name} onChange={set('first_name')} placeholder="Aarav" />
        </Field>
        <Field label="Last name">
          <input value={form.last_name || ''} onChange={set('last_name')} placeholder="Sharma" />
        </Field>
        <Field label="Date of birth" required>
          <input type="date" required max={today()} value={form.date_of_birth} onChange={set('date_of_birth')} />
        </Field>
        <Field label="Gender">
          <select value={form.gender} onChange={set('gender')}>
            <option value="male">Boy</option>
            <option value="female">Girl</option>
            <option value="other">Other</option>
          </select>
        </Field>
        <Field label="Class" hint="The class fee structure is applied automatically on enrolment">
          <select value={form.classroom_id} onChange={set('classroom_id')}>
            <option value="">— Not assigned —</option>
            {classrooms.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Admission date">
          <input type="date" value={form.admission_date || ''} onChange={set('admission_date')} />
        </Field>
        <Field
          label="Fee category"
          hint={freeSeat ? 'This child pays nothing — the fee is set to zero' : 'Concession categories waive the fee entirely'}
        >
          <select value={form.fee_category || 'regular'} onChange={set('fee_category')}>
            {FEE_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
        {student && freeSeat && (
          <div className="alert info full">
            Saving with a concession category clears this child's fee plan and removes
            them from the outstanding dues list. Receipts already issued are untouched.
          </div>
        )}
        {student && (
          <Field label="Status">
            <select value={form.status} onChange={set('status')}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="graduated">Graduated</option>
            </select>
          </Field>
        )}

        {!student && (
          <>
            <div className="section-label">Fee agreement</div>
            <div className="full">
              {freeSeat ? (
                <div className="alert success">
                  <b>{FEE_CATEGORIES.find((c) => c.value === form.fee_category)?.label}</b> — no
                  fee is charged for this child. Nothing to collect now, and they will not
                  appear in the outstanding dues list.
                </div>
              ) : !form.classroom_id ? (
                <div className="alert info">
                  Pick a class above to load its fee structure. You can also enrol without a
                  class and set the fee later from the child's profile.
                </div>
              ) : components.length === 0 ? (
                <div className="alert info">
                  <b>{selectedClass?.name}</b> has no fee structure yet. Set it under
                  <b> Classes &amp; Fees</b>, or just type the total agreed fee below.
                </div>
              ) : (
                <div className="fee-preview">
                  <div className="fee-preview-head">
                    <span>
                      Standard fee for <b>{selectedClass?.name}</b>
                    </span>
                    <b>{money(standardFee)}</b>
                  </div>
                  <table className="data">
                    <tbody>
                      {components.map((c, i) => (
                        <tr key={`${c.name}-${i}`}>
                          <td>{c.name}</td>
                          <td className="muted small">{titleCase(c.frequency)}</td>
                          <td className="num">{money(c.amount)}</td>
                          <td className="num strong">
                            {money(annualTotal([c]))}
                            <span className="muted small"> /yr</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {!freeSeat && (
              <>
            <Field
              label="Total fee agreed with parents"
              required={!!form.classroom_id}
              hint="Pre-filled with the standard fee — change it to whatever was agreed"
            >
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.agreed_fee}
                onChange={set('agreed_fee')}
                placeholder="0.00"
              />
            </Field>
            <Field
              label={difference < 0 ? 'Concession given' : difference > 0 ? 'Above standard by' : 'Difference'}
              hint={
                standardFee > 0
                  ? 'Spread proportionally across all instalments'
                  : 'No standard fee to compare against'
              }
            >
              <input
                readOnly
                value={difference === 0 ? '—' : money(Math.abs(difference))}
                className={difference < 0 ? 'text-green' : difference > 0 ? 'text-red' : ''}
              />
            </Field>
            <Field label="Reason / note for the agreed fee" className="full">
              <input
                value={form.fee_note}
                onChange={set('fee_note')}
                placeholder="Sibling concession, staff ward, early-bird offer…"
              />
            </Field>

            <div className="section-label">First instalment</div>
            <div className="full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.collect_initial}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      collect_initial: e.target.checked,
                      initial_amount:
                        e.target.checked && !f.initial_amount ? String(agreedFee || '') : f.initial_amount,
                    }))
                  }
                />
                Collect the first instalment now and generate a receipt
              </label>
            </div>

            {form.collect_initial && (
              <>
                <Field label="Amount received" required>
                  <input
                    type="number"
                    min="1"
                    step="0.01"
                    required
                    value={form.initial_amount}
                    onChange={set('initial_amount')}
                  />
                </Field>
                <Field label="Payment mode" required>
                  <select value={form.initial_mode} onChange={set('initial_mode')}>
                    {PAYMENT_MODES.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Payment date">
                  <input type="date" max={today()} value={form.initial_date} onChange={set('initial_date')} />
                </Field>
                <Field label="Reference no." hint="Cheque / UPI / transaction reference">
                  <input value={form.initial_reference} onChange={set('initial_reference')} />
                </Field>
                <Field label="Paid towards" className="full" hint="Printed as the particulars on the receipt">
                  <select value={form.initial_particulars} onChange={set('initial_particulars')}>
                    {FEE_PARTICULARS.filter((p) => p.value && p.value !== CUSTOM_PARTICULARS).map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            )}

            {agreedFee > 0 && (
              <div className="full fee-summary-strip">
                <div>
                  <span>Total agreed fee</span>
                  <b>{money(agreedFee)}</b>
                </div>
                <div>
                  <span>Paying now</span>
                  <b className="text-green">
                    {money(form.collect_initial ? initialAmount : 0)}
                  </b>
                </div>
                <div>
                  <span>Balance due</span>
                  <b className={balanceAfter > 0 ? 'text-red' : 'text-green'}>
                    {money(Math.max(0, balanceAfter))}
                  </b>
                </div>
              </div>
            )}
              </>
            )}
          </>
        )}

        <div className="section-label">Daycare</div>
        <div className="full">
          <label className="check">
            <input
              type="checkbox"
              checked={form.daycare_enrolled}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  daycare_enrolled: e.target.checked,
                  daycare_hours: e.target.checked && !f.daycare_hours ? '1' : f.daycare_hours,
                }))
              }
            />
            Stays for daycare
          </label>
          <div className="hint" style={{ marginTop: 4 }}>
            Charged monthly per hour of daily stay, on top of any class fee. A child from
            another school can take daycare on its own — leave the class unassigned.
          </div>
        </div>

        {form.daycare_enrolled && (
          <>
            <Field label="Hours per day" required>
              <input
                type="number"
                min="0.5"
                max={school.daycare_max_hours ?? 12}
                step="0.5"
                required
                value={form.daycare_hours}
                onChange={set('daycare_hours')}
              />
            </Field>
            <Field
              label="Rate per hour / month"
              hint={
                ageYears == null
                  ? 'No date of birth yet — the higher rate is assumed'
                  : `Age ${ageYears.toFixed(1)} · standard rate ${money(suggestedRate)}`
              }
            >
              <input
                type="number"
                min="0"
                step="1"
                value={form.daycare_rate}
                onChange={set('daycare_rate')}
                placeholder={String(suggestedRate)}
              />
            </Field>
            <Field label="Note" className="full">
              <input
                value={form.daycare_note}
                onChange={set('daycare_note')}
                placeholder="e.g. 2pm–5pm, picked up by grandmother"
              />
            </Field>
            {daycareHours > 0 && (
              <div className="full fee-summary-strip">
                <div>
                  <span>Daycare per month</span>
                  <b>{money(daycareMonthly)}</b>
                </div>
                <div>
                  <span>Over 12 months</span>
                  <b>{money(daycareMonthly * 12)}</b>
                </div>
                <div>
                  <span>Working</span>
                  <b className="muted">
                    {daycareHours} × {money(daycareRate)}
                  </b>
                </div>
              </div>
            )}
          </>
        )}

        <div className="section-label">Parents / guardian</div>
        <Field label="Father's name">
          <input value={form.guardian.father_name || ''} onChange={setNested('guardian', 'father_name')} />
        </Field>
        <Field label="Father's occupation">
          <input value={form.guardian.father_occupation || ''} onChange={setNested('guardian', 'father_occupation')} />
        </Field>
        <Field label="Mother's name">
          <input value={form.guardian.mother_name || ''} onChange={setNested('guardian', 'mother_name')} />
        </Field>
        <Field label="Mother's occupation">
          <input value={form.guardian.mother_occupation || ''} onChange={setNested('guardian', 'mother_occupation')} />
        </Field>
        <Field label="Primary contact number" required>
          <input
            required
            value={form.guardian.primary_phone || ''}
            onChange={setNested('guardian', 'primary_phone')}
            placeholder="+91 98765 43210"
          />
        </Field>
        <Field label="Alternate number">
          <input value={form.guardian.alternate_phone || ''} onChange={setNested('guardian', 'alternate_phone')} />
        </Field>
        <Field label="Email">
          <input type="email" value={form.guardian.email || ''} onChange={setNested('guardian', 'email')} />
        </Field>
        <Field label="Guardian (if not a parent)">
          <input value={form.guardian.guardian_name || ''} onChange={setNested('guardian', 'guardian_name')} />
        </Field>
        <Field label="Home address" className="full">
          <textarea value={form.guardian.address || ''} onChange={setNested('guardian', 'address')} rows={2} />
        </Field>

        <div className="section-label">Health & care</div>
        <Field label="Blood group">
          <select value={form.medical.blood_group || ''} onChange={setNested('medical', 'blood_group')}>
            <option value="">— Not known —</option>
            {BLOOD_GROUPS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Allergies" hint="Very important for snack time">
          <input value={form.medical.allergies || ''} onChange={setNested('medical', 'allergies')} placeholder="Peanuts, dust…" />
        </Field>
        <Field label="Medical conditions">
          <input value={form.medical.conditions || ''} onChange={setNested('medical', 'conditions')} />
        </Field>
        <Field label="Doctor's name">
          <input value={form.medical.doctor_name || ''} onChange={setNested('medical', 'doctor_name')} />
        </Field>
        <Field label="Doctor's phone">
          <input value={form.medical.doctor_phone || ''} onChange={setNested('medical', 'doctor_phone')} />
        </Field>

        <div className="section-label">Other</div>
        <Field label="Transport">
          <label className="check" style={{ paddingTop: 8 }}>
            <input
              type="checkbox"
              checked={!!form.transport_opted}
              onChange={(e) => setForm({ ...form, transport_opted: e.target.checked })}
            />
            Uses school van
          </label>
        </Field>
        {form.transport_opted && (
          <Field label="Route">
            <input value={form.transport_route || ''} onChange={set('transport_route')} placeholder="Route 1 - Jayanagar" />
          </Field>
        )}
        <Field label="Notes" className="full">
          <textarea value={form.notes || ''} onChange={set('notes')} rows={2} placeholder="Anything the staff should know…" />
        </Field>
      </form>
    </Modal>
  )
}
