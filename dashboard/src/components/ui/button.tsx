import type { ButtonHTMLAttributes } from "react"

import { cn } from "../../lib/utils"

type ButtonVariant = "default" | "ghost"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md px-3.5 py-2 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70",
        variant === "default" &&
          "bg-primary text-primary-foreground hover:bg-primary/90",
        variant === "ghost" && "bg-transparent text-foreground hover:bg-muted",
        className,
      )}
      {...props}
    />
  )
}
