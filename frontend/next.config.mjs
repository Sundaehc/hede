/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8137"

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ]
  },
  experimental: {
    // AI SQL planning can legitimately exceed Next's 30s development proxy default.
    proxyTimeout: 180_000,
    serverActions: {
      bodySizeLimit: "50mb",
    },
  },
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "192.168.10.229" },
      { protocol: "http", hostname: "127.0.0.1" },
    ],
  },
}

export default nextConfig
