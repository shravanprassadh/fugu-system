/** @type {import('next').NextConfig} */
<<<<<<< Updated upstream
=======

const RAW_API_BASE = process.env.NEXT_PUBLIC_FUGU_API_BASE_URL ?? "";

/*
 * Fail the build loudly on the misconfigurations that previously produced a
 * confusing runtime 404 on /api/auth/login:
 *  - a value without an http(s) scheme,
 *  - a value that ends with /api (the frontend appends /api/... itself),
 *  - a missing value on Vercel, where a backend origin is always required.
 * Local and CI builds may omit the variable; the login screen then surfaces
 * a clear configuration error at runtime instead.
 */
function validateApiBase(value) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    if (process.env.VERCEL) {
      throw new Error(
        "NEXT_PUBLIC_FUGU_API_BASE_URL is not set. Vercel deployments must point at the backend origin, " +
          "for example https://your-render-backend.onrender.com (without a trailing /api). " +
          "Set it in the Vercel project environment variables and redeploy.",
      );
    }
    return;
  }
  if (!/^https?:\/\//.test(trimmed)) {
    throw new Error(
      `NEXT_PUBLIC_FUGU_API_BASE_URL must start with http:// or https://, received "${value}".`,
    );
  }
  if (trimmed.endsWith("/api")) {
    throw new Error(
      `NEXT_PUBLIC_FUGU_API_BASE_URL must not end with /api because the frontend already calls /api/... paths, received "${value}".`,
    );
  }
}

validateApiBase(RAW_API_BASE);

>>>>>>> Stashed changes
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
