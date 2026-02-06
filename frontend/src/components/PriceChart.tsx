import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts'
import type { PriceHistoryPoint } from '../types/events'

interface PriceChartProps {
  priceHistory: PriceHistoryPoint[]
  showProbability?: boolean
  showPriceChange?: boolean
}

export default function PriceChart({
  priceHistory,
  showProbability = true,
  showPriceChange = true,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const priceSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const probSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const changeSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: 'rgba(48, 54, 61, 0.5)' },
        horzLines: { color: 'rgba(48, 54, 61, 0.5)' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#30363d',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      leftPriceScale: {
        visible: true,
        borderColor: '#30363d',
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#30363d',
        timeVisible: true,
        secondsVisible: false,
      },
      handleScale: false,
      handleScroll: false,
    })

    // BTC Price series (left scale, orange)
    const priceSeries = chart.addLineSeries({
      color: '#f7931a',
      lineWidth: 2,
      priceScaleId: 'left',
      title: 'BTC',
    })
    priceSeriesRef.current = priceSeries

    // Probability series (right scale, green/red)
    const probSeries = chart.addLineSeries({
      color: '#3fb950',
      lineWidth: 2,
      priceScaleId: 'right',
      title: 'UP %',
    })
    probSeriesRef.current = probSeries

    // Price change series (right scale, blue dotted)
    const changeSeries = chart.addLineSeries({
      color: '#58a6ff',
      lineWidth: 1,
      lineStyle: 2, // dotted
      priceScaleId: 'right',
      title: 'Change %',
    })
    changeSeriesRef.current = changeSeries

    chartRef.current = chart

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }

    window.addEventListener('resize', handleResize)
    handleResize()

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [])

  // Update data
  useEffect(() => {
    if (!chartRef.current || !priceHistory.length) return

    const priceData: LineData[] = priceHistory.map((p) => ({
      time: (new Date(p.timestamp).getTime() / 1000) as Time,
      value: p.price,
    }))

    const probData: LineData[] = priceHistory.map((p) => ({
      time: (new Date(p.timestamp).getTime() / 1000) as Time,
      value: p.yes_price * 100,
    }))

    const changeData: LineData[] = priceHistory.map((p) => ({
      time: (new Date(p.timestamp).getTime() / 1000) as Time,
      value: p.percent_change,
    }))

    priceSeriesRef.current?.setData(priceData)

    if (showProbability) {
      probSeriesRef.current?.setData(probData)
      probSeriesRef.current?.applyOptions({ visible: true })
    } else {
      probSeriesRef.current?.applyOptions({ visible: false })
    }

    if (showPriceChange) {
      changeSeriesRef.current?.setData(changeData)
      changeSeriesRef.current?.applyOptions({ visible: true })
    } else {
      changeSeriesRef.current?.applyOptions({ visible: false })
    }

    // Update probability line color based on average
    if (probData.length > 0 && showProbability) {
      const avg = probData.reduce((sum, p) => sum + p.value, 0) / probData.length
      probSeriesRef.current?.applyOptions({
        color: avg >= 50 ? '#3fb950' : '#f85149',
      })
    }

    // Add price to beat horizontal line (dashed gray)
    if (priceHistory.length > 0 && priceSeriesRef.current) {
      const ptb = priceHistory[0].price_to_beat
      if (ptb > 0) {
        // Remove existing price lines first
        const existingLines = (priceSeriesRef.current as any)._priceLines || []
        existingLines.forEach((line: any) => {
          try {
            priceSeriesRef.current?.removePriceLine(line)
          } catch {}
        })

        // Create new price line
        const priceLine = priceSeriesRef.current.createPriceLine({
          price: ptb,
          color: '#8b949e',
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: 'Target',
        })
        ;(priceSeriesRef.current as any)._priceLines = [priceLine]
      }
    }

    // Add 50% reference line on probability scale
    if (showProbability && probSeriesRef.current) {
      const existingLines = (probSeriesRef.current as any)._priceLines || []
      existingLines.forEach((line: any) => {
        try {
          probSeriesRef.current?.removePriceLine(line)
        } catch {}
      })

      const fiftyLine = probSeriesRef.current.createPriceLine({
        price: 50,
        color: 'rgba(139, 148, 158, 0.3)',
        lineWidth: 1,
        lineStyle: 2, // Dashed
        axisLabelVisible: false,
        title: '',
      })
      ;(probSeriesRef.current as any)._priceLines = [fiftyLine]
    }

    // Auto-scale price to center on price_to_beat
    if (priceHistory.length > 0) {
      const ptb = priceHistory[0].price_to_beat || priceData[0].value
      const prices = priceData.map((d) => d.value)
      const minP = Math.min(...prices)
      const maxP = Math.max(...prices)
      let halfWindow = 500
      if (maxP - ptb > halfWindow || ptb - minP > halfWindow) {
        halfWindow = 1000
      }
      chartRef.current?.priceScale('left').applyOptions({
        autoScale: false,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      })
    }

    chartRef.current?.timeScale().fitContent()
  }, [priceHistory, showProbability, showPriceChange])

  return <div ref={containerRef} className="chart-container" />
}
