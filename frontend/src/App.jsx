import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectCockpit from './pages/ProjectCockpit'
import RiskRadar from './pages/RiskRadar'
import MapPage from './pages/MapPage'
import Milestones from './pages/Milestones'
import Analytics from './pages/Analytics'
import Bottlenecks from './pages/Bottlenecks'
import { Alerts, Actions } from './pages/AlertsActions'
import Reports from './pages/Reports'
import Copilot from './pages/Copilot'
import DataPage from './pages/DataPage'
import SettingsPage from './pages/SettingsPage'
import Landing from './pages/Landing'

export default function App() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<Layout />}><Route index element={<Dashboard />} /></Route>
      <Route element={<Layout />}>
        <Route path="projects" element={<Projects />} />
        <Route path="projects/:code" element={<ProjectCockpit />} />
        <Route path="risk-radar" element={<RiskRadar />} />
        <Route path="map" element={<MapPage />} />
        <Route path="milestones" element={<Milestones />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="bottlenecks" element={<Bottlenecks />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="actions" element={<Actions />} />
        <Route path="reports" element={<Reports />} />
        <Route path="copilot" element={<Copilot />} />
        <Route path="data" element={<DataPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<div className="card">Page not found.</div>} />
      </Route>
    </Routes>
  )
}
