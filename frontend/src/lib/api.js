import axios from 'axios'

export const TOKEN_KEY = 'preschool.token'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const onLogin = window.location.pathname === '/login'
    if (status === 401 && !onLogin) {
      localStorage.removeItem(TOKEN_KEY)
      window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)

/**
 * Fetch the receipt PDF through axios (so the auth header is sent) and hand it
 * to the browser as a download.
 */
export async function downloadReceiptPdf(paymentId, receiptNo = 'receipt') {
  const { data } = await api.get(`/api/fees/receipts/${paymentId}/pdf`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${String(receiptNo).replace(/[\\/]/g, '-')}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

/** Pull a human-readable message out of any FastAPI / axios error. */
export function errorMessage(error, fallback = 'Something went wrong') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = (d.loc || []).filter((p) => p !== 'body').join('.')
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join(' · ')
  }
  if (error?.code === 'ERR_NETWORK') return 'Cannot reach the server. Is the backend running?'
  return error?.message || fallback
}

export default api
