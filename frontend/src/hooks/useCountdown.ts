import { useState, useEffect } from 'react'

export function useCountdown(endTimeUtc: string | null | undefined) {
  const [remaining, setRemaining] = useState({ minutes: 0, seconds: 0, expired: true })

  useEffect(() => {
    if (!endTimeUtc) {
      setRemaining({ minutes: 0, seconds: 0, expired: true })
      return
    }

    const update = () => {
      const endMs = new Date(endTimeUtc).getTime()
      const nowMs = Date.now()
      const diffMs = endMs - nowMs

      if (diffMs <= 0) {
        setRemaining({ minutes: 0, seconds: 0, expired: true })
      } else {
        const totalSecs = Math.floor(diffMs / 1000)
        setRemaining({
          minutes: Math.floor(totalSecs / 60),
          seconds: totalSecs % 60,
          expired: false,
        })
      }
    }

    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [endTimeUtc])

  return remaining
}
