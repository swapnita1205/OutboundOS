import type { HTMLAttributes } from "react"

import { cn } from "../../lib/utils"

type BadgeVariant = "default" | "success" | "warning" | "destructive" | "outline"

const badgeStyles: Record<BadgeVariant, string> = {
  default: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  destructive: "bg-destructive/15 text-destructive",
  outline: "bg-transparent text-foreground border border-border",
}

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
        badgeStyles[variant],
        className,
      )}
      {...props}
    />
  )
}
