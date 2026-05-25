import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  compress: false,
  async rewrites() {
    return [
      { source: "/riddle/hereiam", destination: "/riddle/hereiam/chapterii.htm" },
      { source: "/riddle/hereiam/", destination: "/riddle/hereiam/chapterii.htm" }
    ];
  }
};

export default nextConfig;
