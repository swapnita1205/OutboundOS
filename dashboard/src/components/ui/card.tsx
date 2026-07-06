import type { HTMLAttributes } from "react"

import { cn } from "../../lib/utils"

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card/80 p-5 text-card-foreground shadow-sm backdrop-blur",
        className,
      )}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold uppercase tracking-wide text-muted-foreground", className)} {...props} />
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-3", className)} {...props} />
}
