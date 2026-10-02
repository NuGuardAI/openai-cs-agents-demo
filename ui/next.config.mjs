import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @type {import('next').NextConfig} */
const nextConfig = (phase) => {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      devIndicators: false,
      async rewrites() {
        const backend = `http://127.0.0.1:${process.env.BACKEND_PORT || "8250"}`;
        return ["/chatkit", "/chatkit/:path*", "/chat", "/login", "/logout", "/me", "/health"].map(
          (source) => ({ source, destination: `${backend}${source}` })
        );
      },
    };
  }

  return { devIndicators: false, output: "export" };
};

export default nextConfig;
