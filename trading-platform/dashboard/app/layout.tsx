import './globals.css';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
        <meta name="description" content="Section 9 Private Trading Terminal — Ghost in the Shell" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="theme-color" content="#0a0a0f" />
        <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%230a0a0f'/><path d='M8 8h16v2H8zM8 14h16v2H8zM8 20h16v2H8z' fill='%2300fff7' opacity='0.8'/><rect x='12' y='10' width='2' height='12' fill='%23ff00ff' opacity='0.6'/></svg>" />
      </head>
      <body className="bg-bg-primary text-text antialiased">{children}</body>
    </html>
  );
}
