/// <reference types="vite/client" />

// Declares the environment variables the app reads, so a typo is a type error.
interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
