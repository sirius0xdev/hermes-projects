'use client';
import { useEffect, useRef } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';

interface Props { data: any[]; height?: number; }

export default function CandlestickChart({ data, height = 350 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#111827' }, textColor: '#94a3b8', fontSize: 11 },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      width: containerRef.current.clientWidth,
      height,
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: '#2a3548', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#2a3548' },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#00d4aa', downColor: '#f44336', borderUpColor: '#00d4aa', borderDownColor: '#f44336',
      wickUpColor: '#00d4aa', wickDownColor: '#f44336',
    });
    candleSeries.setData(data);
    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    resizeObserver.observe(containerRef.current);

    return () => { resizeObserver.disconnect(); chart.remove(); };
  }, [data, height]);

  return <div ref={containerRef} className="w-full" />;
}

