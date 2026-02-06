import type { EventData } from '../types/events'

interface PriceDisplayProps {
  event: EventData
}

export default function PriceDisplay({ event }: PriceDisplayProps) {
  const currentPrice = event.current_price || 0
  const priceToBeat = event.price_to_beat || 0
  const priceDiff = currentPrice - priceToBeat
  const priceUp = priceDiff >= 0
  const changeClass = priceUp ? 'price-change-positive' : 'price-change-negative'
  const changeSymbol = priceUp ? '\u25b2' : '\u25bc'

  const yesPrice = event.yes_price || 0.5
  const noPrice = event.no_price || 0.5

  const formatPrice = (p: number) => p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <div className="price-container">
      <div className="price-box">
        <span className="price-label">PRICE TO BEAT</span>
        <span className="price-value">${formatPrice(priceToBeat)}</span>
      </div>
      <div className="price-box">
        <span className="price-label">CURRENT PRICE</span>
        <span className="price-value price-value-green">${formatPrice(currentPrice)}</span>
        <span className={`price-change ${changeClass}`}>
          {changeSymbol} ${formatPrice(Math.abs(priceDiff))}
        </span>
      </div>
      <div className="price-box">
        <span className="price-label">UP PROBABILITY</span>
        <span className="price-value price-change-positive">
          {(yesPrice * 100).toFixed(1)}%
        </span>
      </div>
      <div className="price-box">
        <span className="price-label">DOWN PROBABILITY</span>
        <span className="price-value price-change-negative">
          {(noPrice * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  )
}
