import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // Local OCR is intentionally sequential on 8 GB Macs, and a verification
    // can include the uploaded document plus several official PDFs. Keep the
    // development rewrite alive for the backend's bounded pipeline instead of
    // aborting at Next.js's 30-second proxy default.
    proxyTimeout: 60 * 60 * 1000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8000/health",
      },
    ];
  },
};

export default nextConfig;
