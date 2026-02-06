export interface OrderBookLevel {
  price: number
  shares: number
  total: number
}

export interface OrderBookData {
  bids: OrderBookLevel[]
  asks: OrderBookLevel[]
  last_price: number
  spread: number
  volume: number
}

export interface PriceHistoryPoint {
  timestamp: string
  price: number
  yes_price: number
  no_price: number
  percent_change: number
  price_to_beat: number
}

export interface EventData {
  name: string
  description: string
  icon: string
  price_history: PriceHistoryPoint[]
  yes_price: number
  no_price: number
  current_price: number
  price_to_beat: number
  last_update: string
  price_change: number
  volume_24h: number
  condition_id: string
  yes_token_id: string
  no_token_id: string
  order_book_yes: OrderBookData | null
  order_book_no: OrderBookData | null
  event_end_utc: string | null
}

export interface SettingsData {
  mode: string
  refresh_rate: number
  chart_options: string[]
}

export interface WSMessage {
  type: 'full_snapshot' | 'price_update' | 'orderbook_update' | 'settings_update'
  event_id: string
  data: Record<string, unknown>
}

export interface OrderRequest {
  event_id: string
  side: 'Buy' | 'Sell'
  outcome: 'up' | 'down'
  order_type: 'market' | 'limit'
  price: number
  shares: number
}

export interface OrderResponse {
  order_id: string
  status: string
  message: string
}

export interface Position {
  outcome: 'Up' | 'Down'
  qty: number
  avg_price: number
  current_price: number
  cost: number
  value: number
  return_value: number
  return_pct: number
}
