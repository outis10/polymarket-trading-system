import { useState, memo } from 'react'
import type { OrderBookData } from '../types/events'

interface OrderBookProps {
  orderBookYes: OrderBookData | null
  orderBookNo: OrderBookData | null
}

function OrderBookContent({ orderBook }: { orderBook: OrderBookData | null }) {
  if (!orderBook) {
    return <div className="order-book-empty">Waiting for order book data...</div>
  }

  const { bids, asks, last_price, volume } = orderBook

  const maxShares = Math.max(
    1,
    ...asks.map((l) => l.shares),
    ...bids.map((l) => l.shares)
  )

  const bestAsk = asks[0]?.price ?? 0.5
  const bestBid = bids[0]?.price ?? 0.49
  const spreadCents = Math.round((bestAsk - bestBid) * 100)
  const midPrice = (bestAsk + bestBid) / 2

  // Reverse asks so highest price is at top
  const asksReversed = [...asks].reverse()

  return (
    <div className="order-book-content">
      <div className="order-book-volume">${(volume / 1000).toFixed(1)}k Vol</div>

      {/* Asks section with scroll */}
      <span className="order-book-section-label order-book-asks-label">
        Asks (Sell Orders)
      </span>
      <div className="order-book-scroll">
        <table className="order-book-table">
          <thead>
            <tr>
              <th>Price</th>
              <th>Shares</th>
              <th>Total</th>
              <th style={{ width: '50%' }}>Depth</th>
            </tr>
          </thead>
          <tbody>
            {asksReversed.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ color: '#8b949e' }}>No asks available</td>
              </tr>
            ) : (
              asksReversed.map((lvl, i) => {
                const depthPct = (lvl.shares / maxShares) * 100
                const isBest = i === asksReversed.length - 1
                return (
                  <tr
                    key={`ask-${lvl.price}`}
                    className={`order-book-row order-book-ask-row ${isBest ? 'order-book-best-ask' : ''}`}
                  >
                    <td>{Math.round(lvl.price * 100)}&cent;</td>
                    <td>{lvl.shares.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td>${lvl.total.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td className="order-book-depth-cell">
                      <div
                        className="order-book-depth-bar order-book-depth-ask"
                        style={{ width: `${depthPct}%` }}
                      />
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Midpoint - always visible */}
      <div className="order-book-midpoint">
        <span className="order-book-midpoint-item">
          <span className="order-book-midpoint-label">Last</span>
          <span className="order-book-midpoint-value">{Math.round(last_price * 100)}&cent;</span>
        </span>
        <span className="order-book-midpoint-item">
          <span className="order-book-midpoint-label">Spread</span>
          <span className="order-book-midpoint-value">{spreadCents}&cent;</span>
        </span>
        <span className="order-book-midpoint-item">
          <span className="order-book-midpoint-label">Mid</span>
          <span className="order-book-midpoint-value">{Math.round(midPrice * 100)}&cent;</span>
        </span>
      </div>

      {/* Bids section with scroll */}
      <span className="order-book-section-label order-book-bids-label">
        Bids (Buy Orders)
      </span>
      <div className="order-book-scroll">
        <table className="order-book-table">
          <thead>
            <tr>
              <th>Price</th>
              <th>Shares</th>
              <th>Total</th>
              <th style={{ width: '50%' }}>Depth</th>
            </tr>
          </thead>
          <tbody>
            {bids.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ color: '#8b949e' }}>No bids available</td>
              </tr>
            ) : (
              bids.map((lvl, i) => {
                const depthPct = (lvl.shares / maxShares) * 100
                const isBest = i === 0
                return (
                  <tr
                    key={`bid-${lvl.price}`}
                    className={`order-book-row order-book-bid-row ${isBest ? 'order-book-best-bid' : ''}`}
                  >
                    <td>{Math.round(lvl.price * 100)}&cent;</td>
                    <td>{lvl.shares.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td>${lvl.total.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    <td className="order-book-depth-cell">
                      <div
                        className="order-book-depth-bar order-book-depth-bid"
                        style={{ width: `${depthPct}%` }}
                      />
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function OrderBook({ orderBookYes, orderBookNo }: OrderBookProps) {
  const [activeTab, setActiveTab] = useState<'up' | 'down'>('up')

  const activeBook = activeTab === 'up' ? orderBookYes : orderBookNo

  return (
    <div className="order-book-card">
      <div className="order-book-header">
        <span className="order-book-title">Order Book</span>
      </div>

      <div className="order-book-tabs">
        <button
          className={`order-book-tab ${activeTab === 'up' ? 'order-book-tab-active' : ''}`}
          onClick={() => setActiveTab('up')}
        >
          &#9650; Trade Up
        </button>
        <button
          className={`order-book-tab ${activeTab === 'down' ? 'order-book-tab-active' : ''}`}
          onClick={() => setActiveTab('down')}
        >
          &#9660; Trade Down
        </button>
      </div>

      <OrderBookContent orderBook={activeBook} />
    </div>
  )
}

export default memo(OrderBook)
