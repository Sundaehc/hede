/** @type {import('next').NextConfig} */
const nextConfig = {
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
