import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import { useAuth } from './context/AuthContext'
import Attendance from './pages/Attendance'
import Classes from './pages/Classes'
import Dashboard from './pages/Dashboard'
import Fees from './pages/Fees'
import Login from './pages/Login'
import ReceiptView from './pages/ReceiptView'
import Receipts from './pages/Receipts'
import Reports from './pages/Reports'
import StudentDetail from './pages/StudentDetail'
import Students from './pages/Students'
import Teachers from './pages/Teachers'
import Users from './pages/Users'

function Protected({ children, adminOnly }) {
  const { user, ready, isAdmin } = useAuth()
  if (!ready) return <Loading label="Starting up…" />
  if (!user) return <Navigate to="/login" replace />
  if (adminOnly && !isAdmin) return <Navigate to="/" replace />
  return children
}

export default function App() {
  const { user, ready } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={ready && user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="students" element={<Students />} />
        <Route path="students/:id" element={<StudentDetail />} />
        <Route path="teachers" element={<Teachers />} />
        <Route path="classes" element={<Classes />} />
        <Route path="fees" element={<Fees />} />
        <Route path="receipts" element={<Receipts />} />
        <Route path="receipts/:id" element={<ReceiptView />} />
        <Route path="attendance" element={<Attendance />} />
        <Route path="reports" element={<Reports />} />
        <Route
          path="users"
          element={
            <Protected adminOnly>
              <Users />
            </Protected>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
