// App configuration, read once at startup (the frontend version of backend/app/config.py).

const apiUrl = import.meta.env.VITE_API_URL

if (!apiUrl) {
  // Fail fast: without this, every request would silently go to "undefined/uploads".
  throw new Error('VITE_API_URL is not set. Add it to frontend/.env.development.')
}

export const config = {
  apiUrl: apiUrl.replace(/\/+$/, ''), // no trailing slash, so paths can always start with "/"
} as const
