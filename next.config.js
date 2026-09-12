/** @type {import('next').NextConfig} */
// v3-staging
const nextConfig = {
  // Include data/ JSON files in the Vercel serverless bundle for all routes
  // (required for filesystem reads in getLiveData and the /api/data route).
  outputFileTracingIncludes: {
    '/**': ['./data/**/*.json'],
  },
}
module.exports = nextConfig
