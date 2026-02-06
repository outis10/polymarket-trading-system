import { useSettingsStore } from '../../stores/useSettingsStore'

export default function Header() {
  const toggleSidebar = useSettingsStore((s) => s.toggleSidebar)

  return (
    <header className="app-header">
      <div className="app-header-left">
        <span className="app-header-title">Polymarket Monitor</span>
        <span className="app-header-subtitle">Real-time Prediction Markets</span>
      </div>
      <button className="settings-btn" onClick={toggleSidebar}>
        Settings
      </button>
    </header>
  )
}
