/** @type {import('next').NextConfig} */
// v3-staging
const nextConfig = {
  experimental: {
    // Include data/ JSON files in the Vercel serverless bundle so the
    // /api/data/[file] route can read them at runtime.
    outputFileTracingIncludes: {
      '/api/data/[file]': ['./data/**/*.json'],
    },
  },
}
module.exports = nextConfig
