import { memo } from 'react'
import type { EventData } from '../types/events'
import { useEventsStore } from '../stores/useEventsStore'
import PriceDisplay from './PriceDisplay'
import Countdown from './Countdown'
import PriceChart from './PriceChart'
import PositionDisplay from './PositionDisplay'
import OrderBook from './OrderBook'
import TradingPanel from './TradingPanel'

const ICON_MAP: Record<string, { className: string; symbol: string }> = {
  btc: { className: 'event-icon event-icon-btc', symbol: '\u20bf' },
  eth: { className: 'event-icon event-icon-eth', symbol: '\u039e' },
  sol: { className: 'event-icon event-icon-sol', symbol: '\u25ce' },
  generic: { className: 'event-icon event-icon-generic', symbol: '\ud83d\udcca' },
}

interface EventCardProps {
  eventId: string
  event: EventData
}

function EventCard({ eventId, event }: EventCardProps) {
  const settings = useEventsStore((s) => s.settings)
  const chartOptions = settings.chart_options || []

  const iconInfo = ICON_MAP[event.icon] || ICON_MAP.generic

  const showProbability = chartOptions.includes('show_probability')
  const showPriceChange = chartOptions.includes('show_price_change')
  const showOrderBook = chartOptions.includes('show_order_book')

  return (
    <div className="event-card">
      {/* Header */}
      <div className="event-header">
        <div className={iconInfo.className}>{iconInfo.symbol}</div>
        <div>
          <div className="event-title">{event.name}</div>
          <div className="event-subtitle">{event.description}</div>
        </div>
      </div>

      {/* Price row: prices + countdown */}
      <div className="price-row">
        <PriceDisplay event={event} />
        <Countdown eventEndUtc={event.event_end_utc} />
      </div>

      {/* Chart */}
      <PriceChart
        priceHistory={event.price_history}
        showProbability={showProbability}
        showPriceChange={showPriceChange}
      />

      {/* Positions */}
      <PositionDisplay eventId={eventId} />

      {/* Bottom row: order book + trading panel */}
      <div className="bottom-row">
        {showOrderBook && (
          <div className="bottom-row-left">
            <OrderBook
              orderBookYes={event.order_book_yes}
              orderBookNo={event.order_book_no}
            />
          </div>
        )}
        <div className={showOrderBook ? 'bottom-row-right' : ''} style={showOrderBook ? {} : { width: '100%', maxWidth: 400 }}>
          <TradingPanel eventId={eventId} event={event} />
        </div>
      </div>
    </div>
  )
}

export default memo(EventCard)
