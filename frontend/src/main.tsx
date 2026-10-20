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
  { path: '/tenants/:tenantId/forms', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/forms/:projectId', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/forms/:projectId/new', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/forms/:projectId/:formId/preview', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/forms/:projectId/:formId/versions/:versionId', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/forms/:projectId/:formId', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/records', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/records/:projectId/new', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/records/:projectId/:recordId/edit', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/records/:projectId/:recordId', element: <CrmShellPage /> },
  { path: '/tenants/:tenantId/records/:projectId', element: <CrmShellPage /> },
])

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  )
}
