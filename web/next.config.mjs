/** @type {import('next').NextConfig} */
const nextConfig = {
  // SHIP-3: the /api proxy used to give up after 30 s (Next's default) - the same as the backend's ePost timeout -
  // so the page showed an error and re-enabled "Create" while the backend could still be buying. 2 minutes leaves
  // the backend room to finish and answer.
  experimental: {
    proxyTimeout: 120_000,
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://backend:8000'
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
