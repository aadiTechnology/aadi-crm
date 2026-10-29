import type { ReactNode } from 'react'

export function StatusBadge({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'info' | 'neutral'
  children: ReactNode
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string
  message: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <p className="empty-title">{title}</p>
      <p>{message}</p>
      {action}
    </div>
  )
}

export function LoadingSkeleton() {
  return (
    <div className="loading-block" aria-hidden="true">
      <span className="skeleton" />
      <span className="skeleton short" />
    </div>
  )
}

export function NavIcon({ name }: { name: 'overview' | 'leads' | 'projects' | 'forms' | 'records' | 'org' | 'roles' }) {
  const path =
    name === 'overview'
      ? 'M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'
      : name === 'leads'
        ? 'M12 12a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 12zm-7 8a7 7 0 0 1 14 0'
        : name === 'projects'
          ? 'M4 7h7l2 2h7v10H4z'
          : name === 'forms'
            ? 'M7 3h7l5 5v13H7zM14 3v5h5M9 13h6M9 17h6'
            : name === 'records'
              ? 'M5 6h14M5 12h14M5 18h10'
              : name === 'roles'
                ? 'M7 3h8l4 4v14H7zM15 3v4h4M9 12h6M9 16h6'
                : 'M4 19V7l8-4 8 4v12M8 19v-6h8v6'
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
