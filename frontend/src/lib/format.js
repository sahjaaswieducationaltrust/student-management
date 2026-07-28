let currencySymbol = '₹'

export function setCurrencySymbol(symbol) {
  if (symbol) currencySymbol = symbol
}

export function money(value, { compact = false } = {}) {
  const n = Number(value || 0)
  if (compact && Math.abs(n) >= 100000) return `${currencySymbol}${(n / 100000).toFixed(2)}L`
  if (compact && Math.abs(n) >= 1000) return `${currencySymbol}${(n / 1000).toFixed(1)}k`
  return (
    currencySymbol +
    n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  )
}

export function formatDate(value, fallback = '—') {
  if (!value) return fallback
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return fallback
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatDateTime(value, fallback = '—') {
  if (!value) return fallback
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return fallback
  return `${formatDate(d)}, ${d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`
}

/** yyyy-mm-dd for <input type="date"> */
export function toInputDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const today = () => toInputDate(new Date())

export function initials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

export function titleCase(value = '') {
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const MODE_LABELS = {
  cash: 'Cash',
  upi: 'UPI',
  card: 'Card',
  cheque: 'Cheque',
  bank_transfer: 'Bank Transfer',
}

/** "upi" -> "UPI", not "Upi". */
export function modeLabel(mode) {
  return MODE_LABELS[mode] ?? titleCase(mode)
}

export const PAYMENT_MODES = [
  { value: 'cash', label: 'Cash' },
  { value: 'upi', label: 'UPI' },
  { value: 'card', label: 'Card' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'bank_transfer', label: 'Bank Transfer' },
]

export const FREQUENCIES = [
  { value: 'one_time', label: 'One time (at admission)' },
  { value: 'monthly', label: 'Monthly (x12)' },
  { value: 'quarterly', label: 'Quarterly (x4)' },
  { value: 'term', label: 'Per term (x3)' },
  { value: 'annual', label: 'Annual (x1)' },
]

export const OCCURRENCES = { one_time: 1, annual: 1, term: 3, quarterly: 4, monthly: 12 }

export function annualTotal(components = []) {
  return components.reduce(
    (sum, c) => sum + Number(c.amount || 0) * (OCCURRENCES[c.frequency] || 1),
    0,
  )
}
