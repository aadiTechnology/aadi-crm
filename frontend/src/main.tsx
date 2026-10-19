import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { CrmShellPage } from '@/features/shell/CrmShellPage'
import '@/styles.css'

const router = createBrowserRouter([
  { path: '/', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/leads', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/projects', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/projects/new', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/projects/:projectId', element: <CrmShellPage /> },
])

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  )
}
