"use client"

import { useLayoutEffect, useRef, type ReactNode } from "react"

const STORAGE_PREFIX = "hede:session-scroll:v1:"
const memoryFallback = new Map<string, string>()
const SCROLL_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End", " ", "Tab"])
let storageGeneration = 0

type ScrollPosition = { top: number; left: number }
type PageScrollPosition = { window: ScrollPosition; containers: Record<string, ScrollPosition> }

function validPosition(value: unknown): value is ScrollPosition {
  if (!value || typeof value !== "object") return false
  const position = value as ScrollPosition
  return Number.isFinite(position.top) && position.top >= 0 && Number.isFinite(position.left) && position.left >= 0
}

function readPosition(key: string): PageScrollPosition | null {
  try {
    const raw = memoryFallback.get(key) ?? window.sessionStorage.getItem(key)
    if (!raw) return null
    const value = JSON.parse(raw) as PageScrollPosition
    if (!validPosition(value?.window) || !value.containers || typeof value.containers !== "object" || Array.isArray(value.containers)) return null
    if (!Object.values(value.containers).every(validPosition)) return null
    return value
  } catch {
    return null
  }
}

function writePosition(key: string, value: PageScrollPosition) {
  const raw = JSON.stringify(value)
  try {
    window.sessionStorage.setItem(key, raw)
    memoryFallback.delete(key)
  } catch {
    memoryFallback.set(key, raw)
  }
}

export function clearSessionScrollPositions() {
  storageGeneration += 1
  memoryFallback.clear()
  try {
    Object.keys(window.sessionStorage)
      .filter((key) => key.startsWith(STORAGE_PREFIX))
      .forEach((key) => window.sessionStorage.removeItem(key))
  } catch {
    return
  }
}

function containerKey(element: HTMLElement, root: HTMLElement): string {
  const explicitKey = element.getAttribute("data-scroll-restoration-key")
  if (explicitKey) return "key:" + explicitKey
  if (element.id) return "id:" + element.id
  const indexes: number[] = []
  let current: HTMLElement | null = element
  while (current && current !== root) {
    const parent: HTMLElement | null = current.parentElement
    if (!parent) break
    indexes.unshift(Array.prototype.indexOf.call(parent.children, current))
    current = parent
  }
  return "path:" + indexes.join(".")
}

function savedContainer(key: string, root: HTMLElement): HTMLElement | null {
  if (key.startsWith("key:")) {
    return Array.from(root.querySelectorAll<HTMLElement>("[data-scroll-restoration-key]"))
      .find((element) => element.getAttribute("data-scroll-restoration-key") === key.slice(4)) ?? null
  }
  if (key.startsWith("id:")) {
    return Array.from(root.querySelectorAll<HTMLElement>("[id]"))
      .find((element) => element.id === key.slice(3)) ?? null
  }
  if (!key.startsWith("path:")) return null
  let element: Element | undefined = root
  for (const part of key.slice(5).split(".")) {
    const index = Number(part)
    if (!Number.isInteger(index) || index < 0) return null
    element = element?.children[index]
  }
  return element instanceof HTMLElement ? element : null
}

export function SessionScrollRestoration({ pathname, userId, children }: { pathname: string; userId: number; children: ReactNode }) {
  const rootRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return
    const storageKey = STORAGE_PREFIX + userId + ":" + pathname
    const generation = storageGeneration
    const savedPosition = readPosition(storageKey)
    const targetPosition: PageScrollPosition = savedPosition ?? { window: { top: 0, left: 0 }, containers: {} }
    let restoring = true
    let confirmed = false
    let restoreFrame: number | null = null
    let saveFrame: number | null = null
    let latestPosition: PageScrollPosition | null = null
    const containerPositions = { ...targetPosition.containers }
    let resizeObserver: ResizeObserver | null = null
    let mutationObserver: MutationObserver | null = null
    const previousRestoration = window.history.scrollRestoration
    window.history.scrollRestoration = "manual"

    const persist = () => {
      if (saveFrame !== null) window.cancelAnimationFrame(saveFrame)
      saveFrame = null
      if (latestPosition && generation === storageGeneration) writePosition(storageKey, latestPosition)
    }

    const capture = (element?: HTMLElement) => {
      if (restoring) return
      if (element) {
        if (element.closest('[role="dialog"], [role="listbox"], [data-scroll-restoration-ignore]')) return
        const key = containerKey(element, root)
        if (element.scrollTop === 0 && element.scrollLeft === 0) {
          delete containerPositions[key]
        } else {
          containerPositions[key] = { top: element.scrollTop, left: element.scrollLeft }
        }
      }
      latestPosition = {
        window: { top: window.scrollY, left: window.scrollX },
        containers: { ...containerPositions },
      }
    }

    const stopRestoring = () => {
      restoring = false
      if (restoreFrame !== null) window.cancelAnimationFrame(restoreFrame)
      restoreFrame = null
      resizeObserver?.disconnect()
      mutationObserver?.disconnect()
      window.removeEventListener("wheel", onUserScroll)
      window.removeEventListener("touchstart", onUserScroll)
      window.removeEventListener("pointerdown", onUserScroll)
      window.removeEventListener("keydown", onKeyDown)
    }

    const scheduleRestore = () => {
      if (restoring && restoreFrame === null) restoreFrame = window.requestAnimationFrame(restore)
    }

    const restore = () => {
      restoreFrame = null
      if (!restoring) return
      const scrollingElement = document.scrollingElement ?? document.documentElement
      const maximumTop = Math.max(0, scrollingElement.scrollHeight - window.innerHeight)
      const maximumLeft = Math.max(0, scrollingElement.scrollWidth - window.innerWidth)
      const top = Math.min(targetPosition.window.top, maximumTop)
      const left = Math.min(targetPosition.window.left, maximumLeft)
      if (Math.abs(window.scrollY - top) > 1 || Math.abs(window.scrollX - left) > 1) {
        window.scrollTo({ top, left, behavior: "instant" })
      }
      let complete = maximumTop + 1 >= targetPosition.window.top && maximumLeft + 1 >= targetPosition.window.left
      for (const [key, position] of Object.entries(targetPosition.containers)) {
        const element = savedContainer(key, root)
        if (!element) {
          complete = false
          continue
        }
        element.scrollTop = Math.min(position.top, Math.max(0, element.scrollHeight - element.clientHeight))
        element.scrollLeft = Math.min(position.left, Math.max(0, element.scrollWidth - element.clientWidth))
        if (Math.abs(element.scrollTop - position.top) > 1 || Math.abs(element.scrollLeft - position.left) > 1) complete = false
      }
      if (complete && confirmed) {
        stopRestoring()
      } else {
        confirmed = complete
        if (complete) scheduleRestore()
      }
    }

    function onUserScroll() {
      stopRestoring()
      capture()
      persist()
    }

    function onKeyDown(event: KeyboardEvent) {
      if (SCROLL_KEYS.has(event.key)) onUserScroll()
    }

    const onScroll = (event: Event) => {
      if (event.target instanceof Node && event.target !== document && !root.contains(event.target)) return
      capture(event.target instanceof HTMLElement ? event.target : undefined)
      if (latestPosition && saveFrame === null) saveFrame = window.requestAnimationFrame(persist)
    }

    const onNavigation = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null
      if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      capture()
      persist()
    }

    const onPageHide = () => {
      capture()
      persist()
    }

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(scheduleRestore)
      resizeObserver.observe(root)
    }
    mutationObserver = new MutationObserver(scheduleRestore)
    mutationObserver.observe(root, { childList: true, subtree: true })
    window.addEventListener("scroll", onScroll, { capture: true, passive: true })
    window.addEventListener("wheel", onUserScroll, { passive: true })
    window.addEventListener("touchstart", onUserScroll, { passive: true })
    window.addEventListener("pointerdown", onUserScroll, { passive: true })
    window.addEventListener("keydown", onKeyDown)
    document.addEventListener("click", onNavigation, true)
    window.addEventListener("pagehide", onPageHide)
    restore()
    scheduleRestore()

    return () => {
      stopRestoring()
      if (saveFrame !== null) window.cancelAnimationFrame(saveFrame)
      persist()
      window.removeEventListener("scroll", onScroll, true)
      document.removeEventListener("click", onNavigation, true)
      window.removeEventListener("pagehide", onPageHide)
      window.history.scrollRestoration = previousRestoration
    }
  }, [pathname, userId])

  return <div ref={rootRef}>{children}</div>
}
