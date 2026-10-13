import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { createQueryClient } from './api/queryClient'
import App from './App.tsx'
import './index.css'

// Created once, outside any component: creating it inside one would throw the cache away
// on every re-render.
const queryClient = createQueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
