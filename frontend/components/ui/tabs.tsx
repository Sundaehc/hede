"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

type TabsContextValue = {
  value: string
  orientation: "horizontal" | "vertical"
  activationMode: "automatic" | "manual"
  registerContent: (value: string, id: string) => void
  getTriggerId: (value: string) => string
  getContentId: (value: string) => string
  setValue: (value: string) => void
}

const TabsContext = React.createContext<TabsContextValue | null>(null)

function useTabsContext() {
  const context = React.useContext(TabsContext)

  if (!context) {
    throw new Error("Tabs components must be used within Tabs")
  }

  return context
}

function Tabs({
  className,
  defaultValue,
  value: valueProp,
  onValueChange,
  children,
  orientation = "horizontal",
  activationMode = "automatic",
  ...props
}: React.ComponentProps<"div"> & {
  defaultValue: string
  value?: string
  onValueChange?: (value: string) => void
  orientation?: "horizontal" | "vertical"
  activationMode?: "automatic" | "manual"
}) {
  const reactId = React.useId()
  const baseId = React.useMemo(() => `tabs-${reactId.replace(/:/g, "")}`, [reactId])
  const [uncontrolledValue, setUncontrolledValue] = React.useState(defaultValue)
  const value = valueProp ?? uncontrolledValue
  const contentIdsRef = React.useRef<Map<string, string>>(new Map())

  const setValue = React.useCallback(
    (nextValue: string) => {
      if (valueProp === undefined) {
        setUncontrolledValue(nextValue)
      }

      onValueChange?.(nextValue)
    },
    [onValueChange, valueProp]
  )

  const registerContent = React.useCallback((nextValue: string, id: string) => {
    contentIdsRef.current.set(nextValue, id)
  }, [])

  const getTriggerId = React.useCallback((nextValue: string) => `${baseId}-trigger-${nextValue}`, [baseId])

  const getContentId = React.useCallback(
    (nextValue: string) => contentIdsRef.current.get(nextValue) ?? `${baseId}-content-${nextValue}`,
    [baseId]
  )

  return (
    <TabsContext.Provider
      value={{
        activationMode,
        getContentId,
        getTriggerId,
        orientation,
        registerContent,
        setValue,
        value,
      }}    >
      <div data-slot="tabs" className={cn("flex flex-col gap-4", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

function TabsList({ className, ...props }: React.ComponentProps<"div">) {
  const { orientation } = useTabsContext()

  return (
    <div
      data-slot="tabs-list"
      role="tablist"
      aria-orientation={orientation}
      className={cn(
        "inline-flex h-10 items-center gap-2 rounded-xl bg-muted p-1 text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  value,
  onClick,
  onKeyDown,
  ...props
}: React.ComponentProps<"button"> & { value: string }) {
  const {
    activationMode,
    getContentId,
    getTriggerId,
    orientation,
    setValue,
    value: selectedValue,
  } = useTabsContext()
  const isSelected = selectedValue === value
  const internalId = getTriggerId(value)
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)


  const moveFocus = React.useCallback(
    (direction: "next" | "prev" | "first" | "last") => {
      const tablist = triggerRef.current?.closest('[role="tablist"]')
      if (!tablist) {
        return
      }

      const triggers = Array.from(
        tablist.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])')
      )

      if (triggers.length === 0) {
        return
      }

      const currentIndex = triggers.findIndex((trigger) => trigger === triggerRef.current)
      if (currentIndex === -1) {
        return
      }

      let nextIndex = currentIndex

      if (direction === "first") {
        nextIndex = 0
      } else if (direction === "last") {
        nextIndex = triggers.length - 1
      } else {
        const delta = direction === "next" ? 1 : -1
        nextIndex = (currentIndex + delta + triggers.length) % triggers.length
      }

      const nextTrigger = triggers[nextIndex]
      nextTrigger.focus()

      if (activationMode === "automatic") {
        const nextValue = nextTrigger.dataset.value
        if (nextValue) {
          setValue(nextValue)
        }
      }
    },
    [activationMode, setValue]
  )

  return (
    <button
      data-slot="tabs-trigger"
      data-value={value}
      ref={triggerRef}
      id={internalId}
      role="tab"
      type="button"
      aria-controls={getContentId(value)}
      aria-selected={isSelected}
      tabIndex={isSelected ? 0 : -1}
      data-state={isSelected ? "active" : "inactive"}
      className={cn(
        "inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm disabled:pointer-events-none disabled:opacity-50",
        className
      )}
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented) {
          setValue(value)
        }
      }}
      onKeyDown={(event) => {
        onKeyDown?.(event)
        if (event.defaultPrevented) {
          return
        }

        const isHorizontal = orientation === "horizontal"

        if ((isHorizontal && event.key === "ArrowRight") || (!isHorizontal && event.key === "ArrowDown")) {
          event.preventDefault()
          moveFocus("next")
          return
        }

        if ((isHorizontal && event.key === "ArrowLeft") || (!isHorizontal && event.key === "ArrowUp")) {
          event.preventDefault()
          moveFocus("prev")
          return
        }

        if (event.key === "Home") {
          event.preventDefault()
          moveFocus("first")
          return
        }

        if (event.key === "End") {
          event.preventDefault()
          moveFocus("last")
          return
        }

        if (activationMode === "manual" && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault()
          setValue(value)
        }
      }}
      {...props}
    />
  )
}

function TabsContent({ className, value, id, ...props }: React.ComponentProps<"div"> & { value: string }) {
  const { getContentId, getTriggerId, registerContent, value: selectedValue } = useTabsContext()
  const contentId = id ?? getContentId(value)

  React.useEffect(() => {
    registerContent(value, contentId)
  }, [contentId, registerContent, value])

  if (selectedValue !== value) {
    return null
  }

  return (
    <div
      data-slot="tabs-content"
      id={contentId}
      role="tabpanel"
      aria-labelledby={getTriggerId(value)}
      tabIndex={0}
      className={cn("outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsContent, TabsList, TabsTrigger }
