"use client"

import { Toaster as Sonner, ToasterProps } from "sonner"

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: 'group toast border-border/60 bg-background text-foreground shadow-sm',
          title: 'text-sm font-medium text-foreground',
          description: 'text-xs text-muted-foreground',
          actionButton: 'bg-foreground text-background text-xs font-medium px-3 py-1.5 rounded-md hover:bg-foreground/90',
          cancelButton: 'text-xs text-muted-foreground',
        },
      }}
      style={{
        "--normal-bg": "var(--popover)",
        "--normal-text": "var(--popover-foreground)",
        "--normal-border": "var(--border)",
      } as React.CSSProperties}
      {...props}
    />
  )
}

export { Toaster }
