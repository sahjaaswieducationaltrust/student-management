import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, Empty, Loading, StatCard } from '../components/ui'
import { useToast } from '../components/Toast'
import api, { errorMessage } from '../lib/api'
import { formatDate, money } from '../lib/format'

export default function Dashboard() {
  const toast = useToast()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/api/dashboard')
      .then(({ data }) => setStats(data))
      .catch((err) => toast.error(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [toast])

  if (loading) return <Loading />
  if (!stats) return <Empty icon="⚠️" title="Could not load the dashboard" />

  const collectedPct = stats.fees_expected
    ? Math.min(100, Math.round((stats.fees_collected / stats.fees_expected) * 100))
    : 0
  const maxTrend = Math.max(1, ...stats.collection_trend.map((t) => t.amount))
  const maxClass = Math.max(1, ...stats.students_by_class.map((c) => c.count))
  const attendancePct = stats.attendance_today_marked
    ? Math.round((stats.attendance_today_present / stats.attendance_today_marked) * 100)
    : 0

  return (
    <div className="stack">
      <div className="grid cols-4">
        <StatCard
          icon="🧒"
          label="Children enrolled"
          value={stats.students_active}
          hint={`${stats.students_total} total on record`}
        />
        <StatCard
          icon="👩‍🏫"
          label="Teachers"
          value={stats.teachers_active}
          hint={`${stats.classrooms} classes running`}
          tone="#fdeee0"
        />
        <StatCard
          icon="💰"
          label="Fees collected"
          value={money(stats.fees_collected, { compact: true })}
          hint={`${money(stats.collected_this_month, { compact: true })} this month`}
          tone="#e7f6ef"
        />
        <StatCard
          icon="⏳"
          label="Outstanding"
          value={money(stats.fees_outstanding, { compact: true })}
          hint={`of ${money(stats.fees_expected, { compact: true })} expected`}
          tone="#fdeceb"
        />
      </div>

      <div className="grid side">
        <Card
          title="Fee collection trend"
          subtitle="Last 6 months"
          actions={
            <Link className="btn sm" to="/reports">
              Full report →
            </Link>
          }
        >
          {stats.collection_trend.length === 0 ? (
            <Empty icon="📈" title="No payments recorded yet" hint="Collected fees will show up here." />
          ) : (
            <div className="trend">
              {stats.collection_trend.map((t) => (
                <div className="col" key={t.month}>
                  <div className="amt">{money(t.amount, { compact: true })}</div>
                  <div className="fill" style={{ height: `${Math.max(4, (t.amount / maxTrend) * 100)}%` }} />
                  <div className="cap">{t.month}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Collection progress" subtitle="Against expected fee for the year">
          <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em' }}>{collectedPct}%</div>
          <div className="progress" style={{ margin: '10px 0 14px' }}>
            <span style={{ width: `${collectedPct}%` }} />
          </div>
          <dl className="kv">
            <dt>Expected</dt>
            <dd>{money(stats.fees_expected)}</dd>
            <dt>Collected</dt>
            <dd className="text-green">{money(stats.fees_collected)}</dd>
            <dt>Outstanding</dt>
            <dd className="text-red">{money(stats.fees_outstanding)}</dd>
            <dt>Today</dt>
            <dd>{money(stats.collected_today)}</dd>
          </dl>
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title="Children per class"
          actions={
            <Link className="btn sm" to="/classes">
              Manage
            </Link>
          }
        >
          {stats.students_by_class.length === 0 ? (
            <Empty icon="🏫" title="No classes yet" hint="Create a class to start enrolling children." />
          ) : (
            stats.students_by_class.map((c) => (
              <div className="bar-row" key={c.name}>
                <div className="bar-label">{c.name}</div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(c.count / maxClass) * 100}%` }} />
                </div>
                <div className="bar-value">{c.count}</div>
              </div>
            ))
          )}
        </Card>

        <Card
          title="Attendance today"
          subtitle={`${stats.attendance_today_present} present of ${stats.attendance_today_marked} marked`}
          actions={
            <Link className="btn sm" to="/attendance">
              Take attendance
            </Link>
          }
        >
          {stats.attendance_today_marked === 0 ? (
            <Empty icon="📋" title="Attendance not taken yet" hint="Mark today's roll call from the Attendance page." />
          ) : (
            <>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{attendancePct}%</div>
              <div className="progress" style={{ marginTop: 10 }}>
                <span style={{ width: `${attendancePct}%` }} />
              </div>
              <p className="small muted" style={{ marginTop: 10 }}>
                {stats.attendance_today_marked - stats.attendance_today_present} child(ren) absent today.
              </p>
            </>
          )}
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title="Recent receipts"
          bodyClass="tight"
          actions={
            <Link className="btn sm" to="/receipts">
              All receipts
            </Link>
          }
        >
          {stats.recent_payments.length === 0 ? (
            <Empty icon="🧾" title="No receipts yet" hint="Collect a fee to generate the first receipt." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th>Child</th>
                    <th className="num">Amount</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_payments.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <Link to={`/receipts/${p.id}`}>{p.receipt_no}</Link>
                      </td>
                      <td>
                        <div className="cell-title">{p.student_name}</div>
                        <div className="cell-sub">{p.classroom_name || '—'}</div>
                      </td>
                      <td className="num">{money(p.amount)}</td>
                      <td className="nowrap">{formatDate(p.paid_on)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="Recent admissions"
          bodyClass="tight"
          actions={
            <Link className="btn sm" to="/students">
              All children
            </Link>
          }
        >
          {stats.recent_admissions.length === 0 ? (
            <Empty icon="🧒" title="No children enrolled yet" hint="Add your first child from the Children page." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Admission no.</th>
                    <th>Class</th>
                    <th>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_admissions.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <Link to={`/students/${s.id}`} className="cell-title">
                          {s.name}
                        </Link>
                      </td>
                      <td className="muted">{s.admission_no}</td>
                      <td>{s.classroom_name || '—'}</td>
                      <td className="nowrap">{formatDate(s.admission_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
