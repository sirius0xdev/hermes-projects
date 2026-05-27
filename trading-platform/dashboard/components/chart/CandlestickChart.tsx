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
    bull: '#00fff7',
    bear: '#ff00ff',
    bullAlpha: 'rgba(0, 255, 247, 0.12)',
    bearAlpha: 'rgba(255, 0, 255, 0.12)',
    grid: 'rgba(0, 255, 247, 0.06)',
    text: '#4a4a6a',
    bg: '#0a0a0f',
    crosshair: '#1a1a3a',
    volumeBull: 'rgba(0, 255, 247, 0.08)',
    volumeBear: 'rgba(255, 0, 255, 0.08)',
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
    const padding = { top: 20, right: 64, bottom: 32, left: 12 };

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
    const volH = chartH * 0.18;

    // Clear
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, containerWidth, height);

    // Grid lines
    const gridLines = 5;
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= gridLines; i++) {
      const y = padding.top + (chartH / gridLines) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(containerWidth - padding.right, y);
      ctx.stroke();

      const price = maxPrice - (adjRange / gridLines) * i;
      ctx.fillStyle = colors.text;
      ctx.font = '10px "JetBrains Mono", ui-monospace, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(
        price < 1 ? price.toFixed(6) : price < 1000 ? price.toFixed(2) : price.toFixed(0),
        containerWidth - padding.right + 10,
        y + 3
      );
    }

    // Time labels
    const visibleCount = Math.min(data.length, Math.floor(chartW / 10));
    const startIdx = data.length - visibleCount;
    const candleW = chartW / visibleCount;
    const bodyW = Math.max(candleW * 0.65, 2);

    ctx.fillStyle = colors.text;
    ctx.font = '9px "JetBrains Mono", ui-monospace, monospace';
    ctx.textAlign = 'center';
    const labelStep = Math.max(1, Math.floor(visibleCount / 6));
    for (let i = 0; i < visibleCount; i += labelStep) {
      const candle = data[startIdx + i];
      const x = padding.left + i * candleW + candleW / 2;
      const d = new Date(candle.time);
      const label = d.getHours() > 0
        ? `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
        : `${d.getMonth()+1}/${d.getDate()}`;
      ctx.fillText(label, x, height - 8);
    }

    // Volume bars
    for (let i = 0; i < visibleCount; i++) {
      const candle = data[startIdx + i];
      const x = padding.left + i * candleW;
      const volBarH = (candle.volume / maxVol) * volH;
      const isBull = candle.close >= candle.open;

      ctx.fillStyle = isBull ? colors.volumeBull : colors.volumeBear;
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
      ctx.lineWidth = candleW > 8 ? 1.2 : 0.8;
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
    <div ref={containerRef} className="w-full rounded-lg overflow-hidden neon-border-cyan">
      <canvas ref={canvasRef} />
    </div>
  );
}