/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    const dataUrl = process.env.DATA_SERVICE_URL || 'http://trading-data-service:8000';
    const execUrl = process.env.EXECUTE_SERVICE_URL || 'http://trading-execute-service:8000';
    const newsUrl = process.env.NEWS_SERVICE_URL || 'http://trading-news-service:8000';
    return [
      { source: '/api/data/:path*', destination: `${dataUrl}/:path*` },
      { source: '/api/execute/:path*', destination: `${execUrl}/:path*` },
      { source: '/api/auth/:path*', destination: `${execUrl}/auth/:path*` },
      { source: '/api/news/:path*', destination: `${newsUrl}/:path*` },
    ];
  },
};
module.exports = nextConfig;
