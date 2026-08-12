import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { initials } from '../lib/format'

const NAV = [
  {
    group: 'Overview',
    items: [{ to: '/', label: 'Dashboard', icon: '🏠', end: true }],
  },
  {
    group: 'People',
    items: [
      { to: '/students', label: 'Children', icon: '🧒' },
      { to: '/teachers', label: 'Teachers', icon: '👩‍🏫' },
      { to: '/classes', label: 'Classes & Fees', icon: '🏫' },
    ],
  },
  {
    group: 'Finance',
    items: [
      { to: '/fees', label: 'Collect Fee', icon: '💳' },
      { to: '/receipts', label: 'Receipts', icon: '🧾' },
      { to: '/reports', label: 'Reports', icon: '📊' },
    ],
  },
  {
    group: 'Daily',
    items: [
      { to: '/attendance', label: 'Attendance', icon: '📋' },
      { to: '/messages', label: 'Message Parents', icon: '💬' },
    ],
  },
  {
    group: 'Admin',
    adminOnly: true,
    items: [{ to: '/users', label: 'Users', icon: '🔐' }],
  },
]

const TITLES = {
  '/': 'Dashboard',
  '/students': 'Children',
  '/teachers': 'Teachers',
  '/classes': 'Classes & Fee Structure',
  '/fees': 'Collect Fee',
  '/receipts': 'Fee Receipts',
  '/reports': 'Reports',
  '/attendance': 'Daily Attendance',
  '/messages': 'Message Parents',
  '/users': 'User Accounts',
}

export default function Layout() {
  const { user, school, logout, isAdmin } = useAuth()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  const title =
    TITLES[pathname] ||
    (pathname.startsWith('/students/') ? 'Child Profile' : '') ||
    (pathname.startsWith('/receipts/') ? 'Fee Receipt' : '') ||
    'Hello Kids'

  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? 'open' : ''}`} onClick={() => setOpen(false)}>
        <div className="sidebar-brand">
          <div className="logo">
            <img src="/hellokids-logo.png" alt="" />
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="name">{school.school_name}</div>
            {school.school_trust && <div className="trust">{school.school_trust}</div>}
            <div className="year">
              {school.school_branch ? `${school.school_branch} · ` : ''}AY {school.academic_year}
            </div>
          </div>
        </div>

        <nav className="nav">
          {NAV.filter((g) => !g.adminOnly || isAdmin).map((group) => (
            <div key={group.group}>
              <div className="nav-group-label">{group.group}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                >
                  <span className="ico">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-user">
          <div className="avatar">{initials(user?.name || '?')}</div>
          <div className="who">
            <b>{user?.name}</b>
            <span>{user?.role}</span>
          </div>
          <button className="btn ghost sm" onClick={logout} title="Sign out">
            ⏻
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            className="btn ghost sm menu-toggle"
            onClick={(e) => {
              e.stopPropagation()
              setOpen((v) => !v)
            }}
          >
            ☰
          </button>
          <div>
            <h1>{title}</h1>
            <div className="sub">{school.school_legal_line || school.school_full_name || school.school_name}</div>
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
