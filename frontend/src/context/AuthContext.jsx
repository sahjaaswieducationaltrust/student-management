import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api, { TOKEN_KEY } from '../lib/api'
import { setCurrencySymbol } from '../lib/format'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [school, setSchool] = useState({
    school_name: 'Hello Kids',
    school_full_name: 'Hello Kids Preschool',
    school_branch: '',
    school_tagline: 'The Power of Early Childhood Education',
    academic_year: '',
    currency_symbol: '₹',
  })
  const [ready, setReady] = useState(false)

  const loadSchool = useCallback(async () => {
    try {
      const { data } = await api.get('/api/settings')
      setSchool(data)
      setCurrencySymbol(data.currency_symbol)
    } catch {
      /* branding is optional — keep the defaults */
    }
  }, [])

  useEffect(() => {
    const boot = async () => {
      const token = localStorage.getItem(TOKEN_KEY)
      if (token) {
        try {
          const { data } = await api.get('/api/auth/me')
          setUser(data)
          await loadSchool()
        } catch {
          localStorage.removeItem(TOKEN_KEY)
        }
      }
      setReady(true)
    }
    boot()
  }, [loadSchool])

  const login = useCallback(
    async (email, password) => {
      const { data } = await api.post('/api/auth/login', { email, password })
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setUser(data.user)
      await loadSchool()
      return data.user
    },
    [loadSchool],
  )

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      school,
      ready,
      login,
      logout,
      isAdmin: user?.role === 'admin',
      canManage: user?.role === 'admin' || user?.role === 'staff',
    }),
    [user, school, ready, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
