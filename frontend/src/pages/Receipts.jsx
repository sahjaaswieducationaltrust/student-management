import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { Card, Empty, Loading, Pagination } from '../components/ui'
import api, { downloadReceiptPdf, errorMessage } from '../lib/api'
import { PAYMENT_MODES, formatDate, modeLabel, money } from '../lib/format'

const PAGE_SIZE = 20

export default function Receipts() {
  const toast = useToast()
  const [data, setData] = useState({ items: [], total: 0, total_amount: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [mode, setMode] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

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
      const { data: res } = await api.get('/api/fees/payments', {
        params: {
          page,
          page_size: PAGE_SIZE,
          search: debounced || undefined,
          mode: mode || undefined,
          date_from: from || undefined,
          date_to: to || undefined,
        },
      })
      setData(res)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [page, debounced, mode, from, to, toast])

  useEffect(() => {
    load()
  }, [load])

  const reset = () => {
    setSearch('')
    setMode('')
    setFrom('')
    setTo('')
    setPage(1)
  }

  return (
    <Card
      title={`Fee receipts (${data.total})`}
      subtitle={`${money(data.total_amount)} collected in the current filter`}
      bodyClass="tight"
    >
      <div className="row" style={{ padding: '14px 16px', borderBottom: '1px solid var(--line)' }}>
        <input
          type="search"
          placeholder="Receipt no., child name, admission no.…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 280 }}
        />
        <select value={mode} onChange={(e) => { setMode(e.target.value); setPage(1) }} style={{ maxWidth: 160 }}>
          <option value="">All modes</option>
          {PAYMENT_MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1) }} style={{ maxWidth: 165 }} title="From date" />
        <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1) }} style={{ maxWidth: 165 }} title="To date" />
        <button className="btn" onClick={reset}>
          Reset
        </button>
      </div>

      {loading ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <Empty
          icon="🧾"
          title="No receipts found"
          hint="Collect a fee payment to generate the first receipt."
          action={
            <Link className="btn primary" to="/fees">
              Collect a fee
            </Link>
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Receipt no.</th>
                  <th>Date</th>
                  <th>Child</th>
                  <th>Class</th>
                  <th>Mode</th>
                  <th>Reference</th>
                  <th className="num">Amount</th>
                  <th className="actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id} style={p.cancelled ? { opacity: 0.55 } : undefined}>
                    <td>
                      <Link to={`/receipts/${p.id}`} className="cell-title">
                        {p.receipt_no}
                      </Link>
                      {p.cancelled && (
                        <span className="badge red" style={{ marginLeft: 6 }}>
                          cancelled
                        </span>
                      )}
                    </td>
                    <td className="nowrap">{formatDate(p.paid_on)}</td>
                    <td>
                      <Link to={`/students/${p.student_id}`}>{p.student_name}</Link>
                      <div className="cell-sub">{p.admission_no}</div>
                    </td>
                    <td>{p.classroom_name || '—'}</td>
                    <td>{modeLabel(p.mode)}</td>
                    <td className="muted">{p.reference || '—'}</td>
                    <td className="num strong">{money(p.amount)}</td>
                    <td className="actions">
                      <Link className="btn sm" to={`/receipts/${p.id}`}>
                        View
                      </Link>{' '}
                      <button
                        className="btn sm"
                        onClick={() =>
                          downloadReceiptPdf(p.id, p.receipt_no).catch((err) =>
                            toast.error(errorMessage(err)),
                          )
                        }
                      >
                        PDF
                      </button>
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
  )
}
