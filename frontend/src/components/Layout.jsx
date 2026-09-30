import { Link, NavLink, Navigate, Outlet } from 'react-router-dom'
import { Activity, BarChart3, Bell, Bot, Database, FileText, Flag, LayoutDashboard, ListChecks, Map, Radar, Settings, Layers, LogOut, Search, CircleHelp } from 'lucide-react'
import { useAuth } from '../services/auth'

const NAV = [
  ['/dashboard', 'Dashboard', LayoutDashboard], ['/projects', 'Projects', Layers], ['/risk-radar', 'Risk Radar', Radar], ['/map', 'Map', Map],
  ['/milestones', 'Milestones', Flag], ['/analytics', 'Analytics', BarChart3], ['/bottlenecks', 'Bottlenecks', Activity],
  ['/alerts', 'Alerts', Bell], ['/actions', 'Actions', ListChecks], ['/reports', 'Reports', FileText], ['/copilot', 'Copilot', Bot],
  ['/data', 'Data', Database], ['/settings', 'Settings', Settings],
]

export default function Layout() {
  const { user, ready, logout } = useAuth()
  if (!ready) return <div className="main">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return (
    <div className="shell">
      <nav className="side" aria-label="Primary">
        <Link to="/" className="brand"><div className="brand-mark">P</div><div><b>PRAGATI</b><small>Portfolio intelligence</small></div></Link>
        <div className="nav-label">Workspace</div>
        {NAV.slice(0, 8).map(([to, label, Icon]) => <NavLink key={to} to={to} end><Icon size={16} />{label}</NavLink>)}
        <div className="nav-label">Manage</div>
        {NAV.slice(8).map(([to, label, Icon]) => <NavLink key={to} to={to} end><Icon size={16} />{label}</NavLink>)}
        <div className="side-help"><CircleHelp size={15} /><span>Need help?<small>Read the workspace guide</small></span></div>
      </nav>
      <div className="main">
        <div className="top"><div className="top-search"><Search size={15} /><span>Search projects, risks, actions…</span><kbd>⌘ K</kbd></div>
          <div className="top-user"><span className="user-avatar">{(user.name || 'U').slice(0, 1).toUpperCase()}</span><span><b>{user.name}</b><small>{user.role}</small></span><button className="icon-button" title="Sign out" onClick={logout}><LogOut size={15} /></button></div></div>
        <Outlet />
      </div>
    </div>
  )
}
