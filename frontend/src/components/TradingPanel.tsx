import { useState, useCallback } from 'react'
import type { EventData, OrderRequest, OrderResponse } from '../types/events'

interface TradingPanelProps {
  eventId: string
  event: EventData
}

export default function TradingPanel({ eventId, event }: TradingPanelProps) {
  const [side, setSide] = useState<'Buy' | 'Sell'>('Buy')
  const [orderType, setOrderType] = useState<'limit' | 'market'>('limit')
  const [outcome, setOutcome] = useState<'up' | 'down'>('up')
  const [limitPrice, setLimitPrice] = useState(event.yes_price || 0.5)
  const [shares, setShares] = useState(0)
  const [tradeResult, setTradeResult] = useState<{ type: string; message: string } | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const yesPrice = event.yes_price || 0.5
  const noPrice = event.no_price || 0.5

  const effectivePrice = orderType === 'market'
    ? (outcome === 'up' ? yesPrice : noPrice)
    : limitPrice

  const totalCost = shares * effectivePrice
  const potentialWin = shares > 0 ? shares * (1 - effectivePrice) : 0

  const handleQuickAmount = (amount: number) => {
    setShares(Math.max(0, shares + amount))
  }

  const handleOutcomeChange = (newOutcome: 'up' | 'down') => {
    setOutcome(newOutcome)
    setLimitPrice(newOutcome === 'up' ? yesPrice : noPrice)
  }

  const handleTrade = useCallback(async () => {
    if (shares <= 0 || isSubmitting) return

    setIsSubmitting(true)
    setTradeResult(null)

    const order: OrderRequest = {
      event_id: eventId,
      side,
      outcome,
      order_type: orderType,
      price: effectivePrice,
      shares,
    }

    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order),
      })

      const data: OrderResponse = await res.json()

      if (res.ok) {
        setTradeResult({
          type: side === 'Buy' ? 'success' : 'warning',
          message: data.message || `Order ${data.status}: ${data.order_id}`,
        })
        setShares(0)
      } else {
        setTradeResult({
          type: 'error',
          message: data.message || 'Order failed',
        })
      }
    } catch (err) {
      setTradeResult({
        type: 'error',
        message: 'Network error',
      })
    } finally {
      setIsSubmitting(false)
    }
  }, [eventId, side, outcome, orderType, effectivePrice, shares, isSubmitting])

  return (
    <div className="trading-panel">
      {/* Header: Buy/Sell tabs + Order type */}
      <div className="trading-panel-header">
        <div className="buy-sell-tabs">
          <button
            className={`buy-sell-tab ${side === 'Buy' ? 'buy-tab-active' : ''}`}
            onClick={() => setSide('Buy')}
          >
            Buy
          </button>
          <button
            className={`buy-sell-tab ${side === 'Sell' ? 'sell-tab-active' : ''}`}
            onClick={() => setSide('Sell')}
          >
            Sell
          </button>
        </div>
        <select
          className="order-type-select"
          value={orderType}
          onChange={(e) => setOrderType(e.target.value as 'limit' | 'market')}
        >
          <option value="market">Market</option>
          <option value="limit">Limit</option>
        </select>
      </div>

      {/* Outcome buttons */}
      <div className="outcome-buttons">
        <button
          className={`outcome-btn outcome-up ${outcome === 'up' ? 'outcome-btn-active' : ''}`}
          onClick={() => handleOutcomeChange('up')}
        >
          <span style={{ marginRight: 4 }}>Up</span>
          <span style={{ fontWeight: 700 }}>{Math.round(yesPrice * 100)}&cent;</span>
        </button>
        <button
          className={`outcome-btn outcome-down ${outcome === 'down' ? 'outcome-btn-active' : ''}`}
          onClick={() => handleOutcomeChange('down')}
        >
          <span style={{ marginRight: 4 }}>Down</span>
          <span style={{ fontWeight: 700 }}>{Math.round(noPrice * 100)}&cent;</span>
        </button>
      </div>

      {/* Limit price input */}
      {orderType === 'limit' && (
        <div className="input-group">
          <div className="input-label-row">
            <label className="input-label">Limit Price</label>
          </div>
          <input
            type="number"
            className="trading-input"
            min={0.01}
            max={0.99}
            step={0.01}
            value={limitPrice}
            onChange={(e) => setLimitPrice(Number(e.target.value))}
          />
        </div>
      )}

      {/* Shares input */}
      <div className="input-group">
        <div className="input-label-row">
          <label className="input-label">Shares</label>
        </div>
        <input
          type="number"
          className="trading-input"
          min={0}
          max={10000}
          step={1}
          value={shares}
          onChange={(e) => setShares(Math.max(0, Number(e.target.value)))}
        />
      </div>

      {/* Quick amount buttons */}
      <div className="quick-amounts">
        <button className="quick-btn" onClick={() => handleQuickAmount(-100)}>-100</button>
        <button className="quick-btn" onClick={() => handleQuickAmount(-10)}>-10</button>
        <button className="quick-btn" onClick={() => handleQuickAmount(10)}>+10</button>
        <button className="quick-btn" onClick={() => handleQuickAmount(100)}>+100</button>
      </div>

      {/* Footer: summary + button pushed to bottom */}
      <div className="trading-panel-footer">
        <hr className="trading-divider" />

        {/* Trade summary */}
        <div className="summary-row">
          <span className="summary-label">Total</span>
          <span className="summary-value">${totalCost.toFixed(2)}</span>
        </div>
        <div className="summary-row">
          <span className="summary-label">To Win</span>
          <span className="summary-value-green">${potentialWin.toFixed(2)}</span>
        </div>

        {/* Trade button */}
        <button
          className="trade-btn"
          disabled={shares === 0 || isSubmitting}
          onClick={handleTrade}
        >
          {isSubmitting ? 'Submitting...' : 'Trade'}
        </button>

        {/* Trade result */}
        {tradeResult && (
          <div className={`trade-toast trade-toast-${tradeResult.type}`}>
            {tradeResult.message}
          </div>
        )}
      </div>
    </div>
  )
}
