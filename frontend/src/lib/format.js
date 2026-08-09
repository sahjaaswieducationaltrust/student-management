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

// Everything except `regular` is a full waiver — picking one zeroes the fee.
// Kept in sync with FeeCategory in backend/app/schemas.py.
export const FEE_CATEGORIES = [
  { value: 'regular', label: 'Regular (pays fee)', free: false },
  { value: 'staff_ward', label: 'Staff ward — free', free: true },
  { value: 'management_ward', label: "Management / Principal's ward — free", free: true },
  { value: 'govt_quota', label: 'Govt quota / RTE — free', free: true },
  { value: 'financial_aid', label: 'Financial aid — free', free: true },
]

export const isFreeCategory = (value) => !!value && value !== 'regular'

export function feeCategoryLabel(value) {
  const found = FEE_CATEGORIES.find((c) => c.value === value)
  if (!found) return 'Regular'
  // The list labels carry a "— free" suffix for the dropdown; badges read
  // better without it.
  return found.label.replace(/\s*—\s*free$/, '').replace(/\s*\(pays fee\)$/, '')
}

// What a payment is collected for — printed as the receipt's particulars.
// The blank value falls back to describing the payment from the instalment
// schedule, which is what the app did before this was selectable.
export const FEE_PARTICULARS = [
  { value: '', label: 'Automatic (from the fee schedule)' },
  { value: '1st Term Fee', label: '1st Term Fee' },
  { value: '2nd Term Fee', label: '2nd Term Fee' },
  { value: '3rd Term Fee', label: '3rd Term Fee' },
  { value: 'Full Payment', label: 'Full Payment' },
  { value: 'Admission Fee', label: 'Admission Fee' },
  { value: 'School Kit / Uniform', label: 'School Kit / Uniform' },
  { value: 'Transport Fee', label: 'Transport Fee' },
  { value: 'Miscellaneous', label: 'Miscellaneous' },
  { value: '__custom__', label: 'Other — type your own…' },
]

export const CUSTOM_PARTICULARS = '__custom__'

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
