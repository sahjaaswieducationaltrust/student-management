import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { Card, Empty, Loading, StatCard } from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { formatDate, modeLabel, money, toInputDate } from '../lib/format'

function monthsAgo(count) {
  const d = new Date()
  d.setMonth(d.getMonth() - count)
  d.setDate(1)
  return toInputDate(d)
}

function csvEscape(value) {
  const text = String(value ?? '')
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadCsv(filename, header, rows) {
  const csv = [header, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 15000)
}

export default function Reports() {
  const toast = useToast()
  const [from, setFrom] = useState(monthsAgo(5))
  const [to, setTo] = useState(toInputDate(new Date()))
  const [summary, setSummary] = useState(null)
  const [dues, setDues] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, d] = await Promise.all([
        api.get('/api/fees/summary', { params: { date_from: from, date_to: to } }),
        api.get('/api/fees/dues'),
      ])
      setSummary(s.data)
      setDues(d.data)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [from, to, toast])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <Loading />
  if (!summary) return <Empty icon="⚠️" title="Could not load reports" />

  const maxMonth = Math.max(1, ...summary.by_month.map((m) => m.amount))
  const totalDue = dues.reduce((sum, d) => sum + d.balance, 0)
  const totalOverdue = dues.reduce((sum, d) => sum + d.overdue_amount, 0)

  const exportDues = () =>
    downloadCsv(
      `outstanding-dues-${toInputDate(new Date())}.csv`,
      ['Admission No', 'Child', 'Class', 'Parent Phone', 'Payable', 'Paid', 'Balance', 'Overdue', 'Next Due'],
      dues.map((d) => [
        d.admission_no,
        d.student_name,
        d.classroom_name || '',
        d.guardian_phone || '',
        d.net_payable,
        d.total_paid,
        d.balance,
        d.overdue_amount,
        d.next_due_date ? formatDate(d.next_due_date) : '',
      ]),
    )

  const exportCollection = () =>
    downloadCsv(
      `collection-${from}-to-${to}.csv`,
      ['Month', 'Receipts', 'Amount'],
      summary.by_month.map((m) => [m.key, m.receipts, m.amount]),
    )

  return (
    <div className="stack">
      <Card title="Report period">
        <div className="row">
          <div className="field">
            <label>From</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="field">
            <label>To</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <div className="row" style={{ alignSelf: 'flex-end' }}>
            <button className="btn" onClick={() => { setFrom(monthsAgo(0)); setTo(toInputDate(new Date())) }}>
              This month
            </button>
            <button className="btn" onClick={() => { setFrom(monthsAgo(5)); setTo(toInputDate(new Date())) }}>
              Last 6 months
            </button>
            <button className="btn" onClick={() => { setFrom(monthsAgo(11)); setTo(toInputDate(new Date())) }}>
              Last 12 months
            </button>
          </div>
        </div>
      </Card>

      <div className="grid cols-4">
        <StatCard icon="💰" label="Collected in period" value={money(summary.total_collected, { compact: true })} hint={`${summary.total_receipts} receipts`} />
        <StatCard icon="🧾" label="Average receipt" value={money(summary.total_receipts ? summary.total_collected / summary.total_receipts : 0, { compact: true })} tone="var(--brand-soft)" />
        <StatCard icon="⏳" label="Outstanding" value={money(totalDue, { compact: true })} hint={`${dues.length} children`} tone="#fdeceb" />
        <StatCard icon="🔴" label="Overdue" value={money(totalOverdue, { compact: true })} hint="Past the due date" tone="#fdf3dc" />
      </div>

      <div className="grid cols-2">
        <Card
          title="Collection by month"
          actions={
            <button className="btn sm" onClick={exportCollection} disabled={!summary.by_month.length}>
              ⬇ CSV
            </button>
          }
        >
          {summary.by_month.length === 0 ? (
            <Empty icon="📈" title="No collection in this period" />
          ) : (
            summary.by_month.map((m) => (
              <div className="bar-row" key={m.key}>
                <div className="bar-label">{m.key}</div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(m.amount / maxMonth) * 100}%` }} />
                </div>
                <div className="bar-value">{money(m.amount, { compact: true })}</div>
              </div>
            ))
          )}
        </Card>

        <Card title="Collection by payment mode">
          {summary.by_mode.length === 0 ? (
            <Empty icon="💳" title="No payments in this period" />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Mode</th>
                    <th className="num">Receipts</th>
                    <th className="num">Amount</th>
                    <th className="num">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_mode.map((m) => (
                    <tr key={m.key}>
                      <td>{modeLabel(m.key)}</td>
                      <td className="num">{m.receipts}</td>
                      <td className="num strong">{money(m.amount)}</td>
                      <td className="num">
                        {summary.total_collected ? Math.round((m.amount / summary.total_collected) * 100) : 0}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card title="Collection by class" bodyClass="tight">
        {summary.by_class.length === 0 ? (
          <Empty icon="🏫" title="No payments in this period" />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Class</th>
                  <th className="num">Receipts</th>
                  <th className="num">Collected</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_class.map((c) => (
                  <tr key={c.key}>
                    <td>{c.key}</td>
                    <td className="num">{c.receipts}</td>
                    <td className="num strong">{money(c.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title={`Outstanding dues (${dues.length})`}
        subtitle={`${money(totalDue)} pending · ${money(totalOverdue)} overdue`}
        bodyClass="tight"
        actions={
          <button className="btn sm" onClick={exportDues} disabled={!dues.length}>
            ⬇ CSV
          </button>
        }
      >
        {dues.length === 0 ? (
          <Empty icon="🎉" title="Everyone is up to date" />
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
                </tr>
              </thead>
              <tbody>
                {dues.slice(0, 50).map((d) => (
                  <tr key={d.student_id}>
                    <td>
                      <Link to={`/students/${d.student_id}`} className="cell-title">
                        {d.student_name}
                      </Link>
                      <div className="cell-sub">{d.admission_no}</div>
                    </td>
                    <td>{d.classroom_name || '—'}</td>
                    <td>{d.guardian_phone || '—'}</td>
                    <td className="num">{money(d.net_payable)}</td>
                    <td className="num text-green">{money(d.total_paid)}</td>
                    <td className="num strong">{money(d.balance)}</td>
                    <td className="num">{d.overdue_amount > 0 ? <span className="text-red">{money(d.overdue_amount)}</span> : '—'}</td>
                    <td className="nowrap">{formatDate(d.next_due_date)}</td>
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
