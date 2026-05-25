'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Candle } from '@/lib/api';

interface CandlestickChartProps {
  data: Candle[];
  height?: number;
}

export default function CandlestickChart({ data, height = 400 }: CandlestickChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);

  const colors = useMemo(() => ({
    bull: '#10b981',
    bear: '#ef4444',
    bullAlpha: 'rgba(16, 185, 129, 0.12)',
    bearAlpha: 'rgba(239, 68, 68, 0.12)',
    grid: '#1e293b',
    text: '#64748b',
    bg: '#0f1117',
    crosshair: '#475569',
    crosshairDash: '#1e293b',
  }), []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx || data.length === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const padding = { top: 16, right: 60, bottom: 30, left: 12 };

    canvas.width = containerWidth * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    const chartW = containerWidth - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Price range
    const prices = data.flatMap(d => [d.high, d.low]);
    let minPrice = Math.min(...prices);
    let maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice || 1;
    minPrice -= priceRange * 0.05;
    maxPrice += priceRange * 0.05;
    const adjRange = maxPrice - minPrice;

    const yScale = (price: number) => padding.top + chartH - ((price - minPrice) / adjRange) * chartH;

    // Volume range
    const volumes = data.map(d => d.volume);
    const maxVol = Math.max(...volumes) * 1.2;
    const volH = chartH * 0.2;

    // Clear
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, containerWidth, height);

    // Grid lines
    const gridLines = 6;
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 0.5;
    ctx.setLineDash([]);
    for (let i = 0; i <= gridLines; i++) {
      const y = padding.top + (chartH / gridLines) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(containerWidth - padding.right, y);
      ctx.stroke();

      const price = maxPrice - (adjRange / gridLines) * i;
      ctx.fillStyle = colors.text;
      ctx.font = '10px ui-monospace, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(
        price < 1 ? price.toFixed(6) : price < 1000 ? price.toFixed(2) : price.toFixed(0),
        containerWidth - padding.right + 8,
        y + 3
      );
    }

    // Time labels
    const visibleCount = Math.min(data.length, Math.floor(chartW / 10));
    const startIdx = data.length - visibleCount;
    const candleW = chartW / visibleCount;
    const bodyW = Math.max(candleW * 0.65, 2);

    ctx.fillStyle = colors.text;
    ctx.font = '9px ui-monospace, monospace';
    ctx.textAlign = 'center';
    const labelStep = Math.max(1, Math.floor(visibleCount / 6));
    for (let i = 0; i < visibleCount; i += labelStep) {
      const candle = data[startIdx + i];
      const x = padding.left + i * candleW + candleW / 2;
      const d = new Date(candle.time);
      const label = d.getHours() > 0
        ? `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`
        : `${d.getMonth()+1}/${d.getDate()}`;
      ctx.fillText(label, x, height - 6);
    }

    // Volume bars
    for (let i = 0; i < visibleCount; i++) {
      const candle = data[startIdx + i];
      const x = padding.left + i * candleW;
      const volBarH = (candle.volume / maxVol) * volH;
      const isBull = candle.close >= candle.open;

      ctx.fillStyle = isBull ? colors.bullAlpha : colors.bearAlpha;
      const volY = padding.top + chartH - volBarH;
      ctx.fillRect(x + (candleW - bodyW) / 2, volY, bodyW, volBarH);
    }

    // Candlesticks
    for (let i = 0; i < visibleCount; i++) {
      const candle = data[startIdx + i];
      const x = padding.left + i * candleW + candleW / 2;
      const isBull = candle.close >= candle.open;
      const color = isBull ? colors.bull : colors.bear;

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(candleW > 12 ? 1.5 : 1, 0.5);
      ctx.beginPath();
      ctx.moveTo(x, yScale(candle.high));
      ctx.lineTo(x, yScale(candle.low));
      ctx.stroke();

      // Body
      const openY = yScale(candle.open);
      const closeY = yScale(candle.close);
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(Math.abs(closeY - openY), 1);

      ctx.fillStyle = color;
      ctx.fillRect(x - bodyW / 2, bodyTop, bodyW, bodyHeight);
    }
  }, [data, containerWidth, height, colors]);

  useEffect(() => {
    draw();
  }, [draw]);

  return (
    <div ref={containerRef} className="w-full">
      <canvas ref={canvasRef} className="rounded-lg" />
    </div>
  );
}
