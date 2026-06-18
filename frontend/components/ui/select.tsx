import * as React from "react"

import { cn } from "@/lib/utils"

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        "flex h-9 w-full cursor-pointer rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-[border-color,box-shadow,background-color] hover:border-ring/55 hover:bg-accent/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60",
        className
      )}
      {...props}
    >
      {children}
    </select>
  )
}

export { Select }
