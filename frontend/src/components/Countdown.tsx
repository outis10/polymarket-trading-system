import { useCountdown } from '../hooks/useCountdown'

interface CountdownProps {
  eventEndUtc: string | null | undefined
}

export default function Countdown({ eventEndUtc }: CountdownProps) {
  const { minutes, seconds, expired } = useCountdown(eventEndUtc)

  if (expired && !eventEndUtc) {
    return null
  }

  return (
    <div className="countdown">
      <div className="countdown-unit">
        <span className="countdown-value">{String(minutes).padStart(2, '0')}</span>
        <span className="countdown-label">MINS</span>
      </div>
      <div className="countdown-unit">
        <span className="countdown-value">{String(seconds).padStart(2, '0')}</span>
        <span className="countdown-label">SECS</span>
      </div>
    </div>
  )
}
