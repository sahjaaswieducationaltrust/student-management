import { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../components/Toast'
import { Card, Empty, Loading } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../lib/api'
import { formatDateTime } from '../lib/format'

/**
 * Parent broadcasts over WhatsApp click-to-chat.
 *
 * Nothing is sent by the server: the WhatsApp Business API needs Meta
 * verification and pre-approved templates, and Indian SMS needs DLT
 * registration. This prepares the message per family and opens the school's
 * own WhatsApp with it filled in, which costs nothing and needs no approval.
 * Each family opened is ticked off so a half-finished round is obvious.
 */
export default function Messages() {
  const toast = useToast()
  const { canManage } = useAuth()

  const [templates, setTemplates] = useState([])
  const [templateKey, setTemplateKey] = useState('holiday')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [classrooms, setClassrooms] = useState([])
  const [classFilter, setClassFilter] = useState('')
  const [duesOnly, setDuesOnly] = useState(false)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [broadcastId, setBroadcastId] = useState(null)
  const [sent, setSent] = useState({})
  const [history, setHistory] = useState([])
  // What this deployment can do. Until MSG91 is configured the page falls back
  // to click-to-chat rather than offering a button that cannot work.
  const [status, setStatus] = useState(null)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    api.get('/api/messages/templates').then(({ data: res }) => {
      setTemplates(res)
      const first = res.find((t) => t.key === 'holiday') || res[0]
      if (first) {
        setBody(first.body)
        setTitle(first.label)
      }
    }).catch((err) => toast.error(errorMessage(err)))
    api.get('/api/classrooms').then(({ data: res }) => setClassrooms(res)).catch(() => {})
    api.get('/api/messages/status').then(({ data: res }) => setStatus(res)).catch(() => {})
  }, [toast])

  const automated = !!status && status.enabled && (status.whatsapp_ready || status.sms_ready)

  const loadHistory = useCallback(async () => {
    try {
      const { data: res } = await api.get('/api/messages/broadcasts', { params: { limit: 10 } })
      setHistory(res)
    } catch {
      /* history is a nicety — never block composing on it */
    }
  }, [])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // Re-render the per-family preview as the message is typed.
  useEffect(() => {
    if (!body.trim()) {
      setData(null)
      return undefined
    }
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const { data: res } = await api.get('/api/messages/recipients', {
          params: {
            body,
            classroom_id: classFilter || undefined,
            dues_only: duesOnly,
          },
        })
        setData(res)
      } catch (err) {
        toast.error(errorMessage(err))
      } finally {
        setLoading(false)
      }
    }, 400)
    return () => clearTimeout(t)
  }, [body, classFilter, duesOnly, toast])

  const pickTemplate = (key) => {
    setTemplateKey(key)
    const found = templates.find((t) => t.key === key)
    if (found) {
      setBody(found.body)
      setTitle(found.label)
      // A new message is a new round of sending.
      setBroadcastId(null)
      setSent({})
    }
  }

  const reachable = useMemo(
    () => (data?.recipients || []).filter((r) => r.whatsapp),
    [data],
  )
  const unreachable = useMemo(
    () => (data?.recipients || []).filter((r) => !r.whatsapp),
    [data],
  )
  const sentCount = reachable.filter((r) => sent[r.student_id]).length

  /** Create the log row once, on the first family opened. */
  const ensureBroadcast = async () => {
    if (broadcastId) return broadcastId
    const { data: created } = await api.post('/api/messages/broadcasts', {
      title: title.trim() || 'Announcement',
      body,
      channel: 'whatsapp',
      recipients: reachable.map((r) => ({
        student_id: r.student_id,
        child_name: r.child_name,
        whatsapp: r.whatsapp,
        sent: false,
      })),
    })
    setBroadcastId(created.id)
    return created.id
  }

  const openWhatsApp = async (recipient) => {
    // Opened first: a popup blocker is far likelier to bite after an await.
    window.open(
      `https://wa.me/${recipient.whatsapp}?text=${encodeURIComponent(recipient.message)}`,
      '_blank',
      'noopener,noreferrer',
    )
    setSent((s) => ({ ...s, [recipient.student_id]: true }))
    try {
      const id = await ensureBroadcast()
      await api.post(`/api/messages/broadcasts/${id}/sent/${recipient.student_id}`)
      loadHistory()
    } catch (err) {
      // The chat is already open; the tick is only bookkeeping.
      toast.error(`Opened, but could not record it: ${errorMessage(err)}`)
    }
  }

  const sendToEveryone = async () => {
    setSending(true)
    setResult(null)
    try {
      const { data: broadcast } = await api.post('/api/messages/send', {
        title: title.trim() || 'Announcement',
        body,
        classroom_id: classFilter || undefined,
        dues_only: duesOnly,
      })
      setResult(broadcast)
      const failed = broadcast.total - broadcast.sent_count
      if (failed > 0) {
        toast.error(`${broadcast.sent_count} sent, ${failed} did not go through`)
      } else {
        toast.success(`Sent to ${broadcast.sent_count} parent(s)`)
      }
      loadHistory()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${label} copied`)
    } catch {
      toast.error('Could not copy — your browser blocked clipboard access')
    }
  }

  return (
    <div className="stack">
      <Card
        title="Message parents"
        subtitle="Holidays, events and reminders over WhatsApp"
      >
        {!automated ? (
          <div className="alert info">
            <b>Manual mode.</b> Messages go from <b>your own WhatsApp</b>, one family at a
            time, at no cost. Automated sending needs an MSG91 account with DLT registration
            and Meta-approved templates — see DEPLOY.md. Until then each family you open is
            ticked off below so you can see where you stopped.
          </div>
        ) : status.dry_run ? (
          <div className="alert error">
            <b>Dry run is on.</b> Pressing send will record a full round and report success
            without any message leaving the building. Set <code>MESSAGING_DRY_RUN=false</code>{' '}
            in Render once you are happy with what it reports.
          </div>
        ) : (
          <div className="alert success">
            <b>Automated sending is live.</b> Messages go out over{' '}
            {status.whatsapp_ready ? 'WhatsApp' : 'SMS'}
            {status.whatsapp_ready && status.sms_ready && status.sms_fallback
              ? ', falling back to SMS for parents it cannot reach'
              : ''}
            . Each message costs money — check the recipient list before sending.
          </div>
        )}

        <div className="form-grid" style={{ marginTop: 14 }}>
          <div className="field">
            <label>Template</label>
            <select value={templateKey} onChange={(e) => pickTemplate(e.target.value)}>
              {templates.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Title (for your records)</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              placeholder="e.g. Independence Day holiday"
            />
          </div>
          <div className="field">
            <label>Class</label>
            <select
              value={classFilter}
              onChange={(e) => {
                setClassFilter(e.target.value)
                setBroadcastId(null)
                setSent({})
              }}
            >
              <option value="">All classes</option>
              {classrooms.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Only families with dues</label>
            <label className="check" style={{ paddingTop: 8 }}>
              <input
                type="checkbox"
                checked={duesOnly}
                onChange={(e) => {
                  setDuesOnly(e.target.checked)
                  setBroadcastId(null)
                  setSent({})
                }}
              />
              Skip families who are fully paid
            </label>
          </div>

          <div className="field full">
            <label>Message</label>
            <textarea
              rows={8}
              value={body}
              onChange={(e) => {
                setBody(e.target.value)
                setBroadcastId(null)
                setSent({})
              }}
              style={{ fontFamily: 'inherit', lineHeight: 1.5 }}
            />
            <div className="hint">
              <code>{'{child}'}</code>, <code>{'{parent}'}</code>, <code>{'{class}'}</code>,{' '}
              <code>{'{school}'}</code> and <code>{'{admission_no}'}</code> are filled in for
              each family.
            </div>
          </div>
        </div>

        {data?.blanks?.length > 0 && (
          <div className="alert error" style={{ marginTop: 12 }}>
            Still to fill in: <b>{data.blanks.join(', ')}</b> — replace these before sending.
          </div>
        )}
      </Card>

      {result && (
        <Card
          title="Delivery report"
          subtitle={`${result.sent_count} of ${result.total} delivered${
            result.recipients.some((r) => r.dry_run) ? ' — dry run, nothing actually sent' : ''
          }`}
          bodyClass="tight"
          actions={
            <button className="btn sm" onClick={() => setResult(null)}>
              Dismiss
            </button>
          }
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Child</th>
                  <th>Channel</th>
                  <th>Result</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {result.recipients.map((r) => (
                  <tr key={r.student_id}>
                    <td className="cell-title">{r.child_name}</td>
                    <td>{r.channel === 'none' ? '—' : r.channel || '—'}</td>
                    <td>
                      {r.status === 'sent' ? (
                        <span className="badge green">sent</span>
                      ) : r.status === 'skipped' ? (
                        <span className="badge">skipped</span>
                      ) : (
                        <span className="badge red">failed</span>
                      )}
                    </td>
                    <td className="small muted">{r.detail || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {loading && <Loading label="Preparing messages…" />}

      {data && !loading && (
        <Card
          title={`Recipients (${data.total})`}
          subtitle={
            `${data.reachable} reachable on WhatsApp` +
            (data.unreachable ? ` · ${data.unreachable} with an unusable number` : '') +
            (sentCount ? ` · ${sentCount} of ${data.reachable} opened` : '')
          }
          bodyClass="tight"
          actions={
            <div className="row">
              {automated && canManage && (
                <button
                  className="btn primary"
                  onClick={sendToEveryone}
                  disabled={sending || reachable.length === 0 || data.blanks?.length > 0}
                  title={
                    data.blanks?.length
                      ? 'Fill in the blanks first'
                      : `Send to ${reachable.length} parent(s)`
                  }
                >
                  {sending ? (
                    <span className="spinner" />
                  ) : (
                    `📤 Send to all ${reachable.length}`
                  )}
                </button>
              )}
              <button
                className="btn sm"
                onClick={() => copy(body, 'Message')}
                title="Copy the raw message"
              >
                Copy message
              </button>
              <button
                className="btn sm"
                onClick={() =>
                  copy(reachable.map((r) => r.whatsapp).join(', '), 'Numbers')
                }
                disabled={reachable.length === 0}
              >
                Copy numbers
              </button>
            </div>
          }
        >
          {data.total === 0 ? (
            <Empty
              icon="👪"
              title="No families match"
              hint="Change the class filter, or untick the dues-only option."
            />
          ) : (
            <>
              {sentCount > 0 && (
                <div className="progress" style={{ margin: '0 16px 12px' }}>
                  <span style={{ width: `${Math.round((sentCount / data.reachable) * 100)}%` }} />
                </div>
              )}
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Child</th>
                      <th>Class</th>
                      <th>Parent</th>
                      <th>Number</th>
                      <th className="actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.recipients.map((r) => (
                      <tr key={r.student_id} style={sent[r.student_id] ? { opacity: 0.55 } : undefined}>
                        <td>
                          <div className="cell-title">{r.child_name}</div>
                          <div className="cell-sub">{r.admission_no}</div>
                        </td>
                        <td>{r.classroom_name || '—'}</td>
                        <td>{r.guardian_name || '—'}</td>
                        <td className="nowrap">
                          {r.whatsapp ? (
                            r.phone
                          ) : (
                            <span className="text-red" title="Not a valid Indian mobile number">
                              {r.phone || 'No number'} ⚠
                            </span>
                          )}
                        </td>
                        <td className="actions">
                          {!r.whatsapp ? (
                            <span className="muted small">Fix the number</span>
                          ) : sent[r.student_id] ? (
                            <span className="badge green">opened ✓</span>
                          ) : (
                            canManage && (
                              <button className="btn sm primary" onClick={() => openWhatsApp(r)}>
                                WhatsApp →
                              </button>
                            )
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {unreachable.length > 0 && (
                <div className="alert error" style={{ margin: 16 }}>
                  <b>{unreachable.length} famil{unreachable.length === 1 ? 'y' : 'ies'}</b> cannot
                  be reached: {unreachable.map((r) => r.child_name).join(', ')}. Their guardian
                  phone number is missing or is not a valid Indian mobile — correct it on the
                  child's profile.
                </div>
              )}
            </>
          )}
        </Card>
      )}

      <Card title="Recent broadcasts" subtitle="What has been sent, and to how many" bodyClass="tight">
        {history.length === 0 ? (
          <Empty icon="📣" title="Nothing sent yet" hint="Your announcements will be listed here." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Announcement</th>
                  <th>Sent by</th>
                  <th>When</th>
                  <th className="num">Opened</th>
                </tr>
              </thead>
              <tbody>
                {history.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <div className="cell-title">{b.title}</div>
                      <div className="cell-sub">{b.body.slice(0, 70)}…</div>
                    </td>
                    <td>{b.created_by || '—'}</td>
                    <td className="nowrap">{formatDateTime(b.created_at)}</td>
                    <td className="num">
                      {b.sent_count} / {b.total}
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
