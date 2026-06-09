"use client"

import * as React from "react"
import { createPortal } from "react-dom"

import { cn } from "@/lib/utils"

type DialogContextValue = {
  contentId: string
  descriptionId: string
  open: boolean
  setDescriptionId: (id: string) => void
  setOpen: (open: boolean) => void
  setTitleId: (id: string) => void
  titleId: string
  triggerRef: React.MutableRefObject<HTMLButtonElement | null>
}

const DialogContext = React.createContext<DialogContextValue | null>(null)

function useDialogContext() {
  const context = React.useContext(DialogContext)

  if (!context) {
    throw new Error("Dialog components must be used within Dialog")
  }

  return context
}

function composeRefs<T>(...refs: Array<React.Ref<T> | undefined>) {
  return (value: T) => {
    refs.forEach((ref) => {
      if (!ref) {
        return
      }

      if (typeof ref === "function") {
        ref(value)
        return
      }

      ;(ref as React.MutableRefObject<T>).current = value
    })
  }
}

function Dialog({
  children,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
}: {
  children: React.ReactNode
  defaultOpen?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const reactId = React.useId()
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen)
  const [titleId, setTitleId] = React.useState("")
  const [descriptionId, setDescriptionId] = React.useState("")
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)
  const open = openProp ?? uncontrolledOpen
  const contentId = React.useMemo(() => `dialog-${reactId.replace(/:/g, "")}-content`, [reactId])

  const setOpen = React.useCallback(
    (nextOpen: boolean) => {
      if (openProp === undefined) {
        setUncontrolledOpen(nextOpen)
      }

      onOpenChange?.(nextOpen)
    },
    [onOpenChange, openProp]
  )

  const value = React.useMemo(
    () => ({
      contentId,
      descriptionId,
      open,
      setDescriptionId,
      setOpen,
      setTitleId,
      titleId,
      triggerRef,
    }),
    [contentId, descriptionId, open, setOpen, titleId]
  )

  return <DialogContext.Provider value={value}>{children}</DialogContext.Provider>
}

const DialogTrigger = React.forwardRef<HTMLButtonElement, React.ComponentProps<"button">>(function DialogTrigger(
  { onClick, ...props },
  ref
) {
  const { contentId, open, setOpen, triggerRef } = useDialogContext()

  return (
    <button
      data-slot="dialog-trigger"
      ref={composeRefs(ref, triggerRef)}
      type="button"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={contentId}
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented) {
          setOpen(true)
        }
      }}
      {...props}
    />
  )
})

function DialogPortal({ children }: { children: React.ReactNode }) {
  if (typeof document === "undefined") {
    return null
  }

  return createPortal(children, document.body)
}

const DialogContent = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(function DialogContent(
  { className, children, onKeyDown, ...props },
  ref
) {
  const { contentId, descriptionId, open, setOpen, titleId, triggerRef } = useDialogContext()
  const contentRef = React.useRef<HTMLDivElement | null>(null)
  const composedRef = composeRefs(ref, contentRef)

  React.useEffect(() => {
    if (!open) {
      return
    }

    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const container = contentRef.current
    const trigger = triggerRef.current
    if (!container) {
      return
    }

    const focusTarget = container.querySelector<HTMLElement>(
      "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
    )

    ;(focusTarget ?? container).focus()

    return () => {
      if (trigger) {
        trigger.focus()
        return
      }

      previouslyFocused?.focus()
    }
  }, [open, triggerRef])

  React.useEffect(() => {
    if (!open) {
      return
    }

    const handleFocusIn = (event: FocusEvent) => {
      const container = contentRef.current
      const target = event.target

      if (!(target instanceof Node) || !container || container.contains(target)) {
        return
      }

      event.preventDefault()
      container.focus()
    }

    document.addEventListener("focusin", handleFocusIn)

    return () => {
      document.removeEventListener("focusin", handleFocusIn)
    }
  }, [open])

  React.useEffect(() => {
    if (!open) {
      return
    }

    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    return () => {
      document.body.style.overflow = originalOverflow
    }
  }, [open])

  if (!open) {
    return null
  }

  return (
    <DialogPortal>
      <div data-slot="dialog-portal" className="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6">
        <button
          aria-hidden="true"
          tabIndex={-1}
          type="button"
          data-slot="dialog-overlay"
          className="absolute inset-0 bg-black/50"
          onClick={() => setOpen(false)}
        />
        <div
          data-slot="dialog-content"
          ref={composedRef}
          id={contentId}
          role="dialog"
          aria-modal="true"
          aria-describedby={descriptionId || undefined}
          aria-labelledby={titleId || undefined}
          tabIndex={-1}
          className={cn(
            "relative z-10 w-full max-w-lg rounded-xl border border-border bg-background p-6 shadow-lg outline-none",
            className
          )}
          onKeyDown={(event) => {
            onKeyDown?.(event)
            if (!event.defaultPrevented && event.key === "Escape") {
              event.preventDefault()
              setOpen(false)
            }
          }}
          {...props}
        >
          {children}
        </div>
      </div>
    </DialogPortal>
  )
})

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="dialog-header" className={cn("flex flex-col gap-2", className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="dialog-footer" className={cn("flex items-center justify-end gap-2", className)} {...props} />
}

const DialogTitle = React.forwardRef<HTMLHeadingElement, React.ComponentProps<"h2">>(function DialogTitle(
  { className, id, ...props },
  ref
) {
  const { setTitleId } = useDialogContext()
  const generatedId = React.useId()
  const titleId = id ?? `dialog-title-${generatedId.replace(/:/g, "")}`

  React.useEffect(() => {
    setTitleId(titleId)

    return () => setTitleId("")
  }, [setTitleId, titleId])

  return <h2 data-slot="dialog-title" ref={ref} id={titleId} className={cn("text-lg font-semibold", className)} {...props} />
})

const DialogDescription = React.forwardRef<HTMLParagraphElement, React.ComponentProps<"p">>(function DialogDescription(
  { className, id, ...props },
  ref
) {
  const { setDescriptionId } = useDialogContext()
  const generatedId = React.useId()
  const descriptionId = id ?? `dialog-description-${generatedId.replace(/:/g, "")}`

  React.useEffect(() => {
    setDescriptionId(descriptionId)

    return () => setDescriptionId("")
  }, [descriptionId, setDescriptionId])

  return (
    <p
      data-slot="dialog-description"
      ref={ref}
      id={descriptionId}
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
})

const DialogClose = React.forwardRef<HTMLButtonElement, React.ComponentProps<"button">>(function DialogClose(
  { onClick, ...props },
  ref
) {
  const { setOpen } = useDialogContext()

  return (
    <button
      data-slot="dialog-close"
      ref={ref}
      type="button"
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented) {
          setOpen(false)
        }
      }}
      {...props}
    />
  )
})

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
}
