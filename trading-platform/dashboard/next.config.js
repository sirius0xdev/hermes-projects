/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    return [
      { source: '/api/data/:path*', destination: 'http://trading-data-service:8000/:path*' },
      { source: '/api/execute/:path*', destination: 'http://trading-execute-service:8000/:path*' },
      { source: '/api/news/:path*', destination: 'http://trading-news-service:8000/:path*' },
    ];
  },
};
module.exports = nextConfig;
