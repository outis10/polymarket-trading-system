import { useWebSocket } from './hooks/useWebSocket'
import { useEventsStore } from './stores/useEventsStore'
import Header from './components/layout/Header'
import Sidebar from './components/layout/Sidebar'
import EventCard from './components/EventCard'

export default function App() {
  const { send } = useWebSocket()
  const events = useEventsStore((s) => s.events)
  const settings = useEventsStore((s) => s.settings)

  return (
    <>
      <Header />
      <Sidebar send={send} />

      {settings.mode === 'demo' && (
        <div className="demo-banner">
          Demo Mode - Showing simulated data for testing purposes
        </div>
      )}

      <div className="event-grid">
        {Object.entries(events).map(([eventId, eventData]) => (
          <EventCard key={eventId} eventId={eventId} event={eventData} />
        ))}
      </div>
    </>
  )
}
