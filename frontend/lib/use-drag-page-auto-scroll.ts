"use client"

import { useEffect } from "react"

const EDGE_SIZE = 96
const MAX_SPEED = 720 // CSS pixels per second.

/** Keep native row drags moving through long pages, even with a stationary pointer. */
export function useDragPageAutoScroll(active: boolean) {
  useEffect(() => {
    if (!active) return

    let pointerY: number | null = null
    let frame: number | null = null
    let previousTime: number | null = null
    let finished = false

    const stop = () => {
      if (frame !== null) window.cancelAnimationFrame(frame)
      frame = null
      pointerY = null
      previousTime = null
    }

    const finish = () => {
      finished = true
      stop()
    }

    const scroll = (time: number) => {
      frame = null
      if (pointerY === null || finished) return

      const height = window.innerHeight
      const edge = Math.min(EDGE_SIZE, height / 4)
      const velocity =
        pointerY < edge
          ? -Math.min(1, (edge - pointerY) / edge)
          : pointerY > height - edge
            ? Math.min(1, (pointerY - height + edge) / edge)
            : 0
      if (!velocity) {
        previousTime = null
        return
      }

      const elapsed =
        previousTime === null ? 16 : Math.min(32, time - previousTime)
      previousTime = time
      const maximum = Math.max(
        0,
        Math.max(
          document.documentElement.scrollHeight,
          document.body.scrollHeight
        ) - height
      )
      const next = Math.max(
        0,
        Math.min(
          maximum,
          window.scrollY + (velocity * MAX_SPEED * elapsed) / 1000
        )
      )
      if (next === window.scrollY) {
        previousTime = null
        return
      }

      // Bypass inner overflow wrappers and any CSS smooth-scroll setting.
      window.scrollTo({ top: next, behavior: "instant" })
      frame = window.requestAnimationFrame(scroll)
    }

    const trackPointer = (event: DragEvent) => {
      if (finished) return
      if (
        event.clientY < 0 ||
        event.clientY > window.innerHeight ||
        event.clientX < 0 ||
        event.clientX > window.innerWidth
      ) {
        stop()
        return
      }
      pointerY = event.clientY
      if (frame === null) frame = window.requestAnimationFrame(scroll)
    }

    const leavePage = (event: DragEvent) => {
      if (
        event.target === document.documentElement &&
        event.relatedTarget === null
      )
        stop()
    }

    const visibilityChanged = () => {
      if (document.hidden) stop()
    }

    document.addEventListener("dragover", trackPointer, true)
    document.addEventListener("dragleave", leavePage, true)
    document.addEventListener("drop", finish, true)
    document.addEventListener("dragend", finish, true)
    document.addEventListener("visibilitychange", visibilityChanged)
    window.addEventListener("blur", stop)
    return () => {
      stop()
      document.removeEventListener("dragover", trackPointer, true)
      document.removeEventListener("dragleave", leavePage, true)
      document.removeEventListener("drop", finish, true)
      document.removeEventListener("dragend", finish, true)
      document.removeEventListener("visibilitychange", visibilityChanged)
      window.removeEventListener("blur", stop)
    }
  }, [active])
}
