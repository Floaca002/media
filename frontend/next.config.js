/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "image.tmdb.org" },
      // Vault's own backend, proxying Jellyfin poster images (see
      // /api/library/items/{id}/image). Add your real domain/host here
      // too if you deploy this behind something other than localhost.
      { protocol: "http", hostname: "localhost" },
    ],
  },
};

module.exports = nextConfig;
