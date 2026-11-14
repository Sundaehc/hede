import { act, cleanup, fireEvent, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { useDragPageAutoScroll } from "./use-drag-page-auto-scroll"

let top = 400
let time = 0
let frameId = 0
let frames: Map<number, FrameRequestCallback>

function nextFrame() {
  time += 16
  act(() => {
    const pending = [...frames.values()]
    frames.clear()
    pending.forEach((callback) => callback(time))
  })
}

function dragAt(y: number) {
  fireEvent(
    document.body,
    new MouseEvent("dragover", {
      bubbles: true,
      clientX: 500,
      clientY: y,
    })
  )
}

beforeEach(() => {
  top = 400
  time = 0
  frameId = 0
  frames = new Map()
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(800)
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(1200)
  vi.spyOn(window, "scrollY", "get").mockImplementation(() => top)
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(
    2600
  )
  vi.spyOn(window, "scrollTo").mockImplementation(
    (options: number | ScrollToOptions) => {
      if (typeof options === "object") top = options.top ?? top
    }
  )
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    frames.set(++frameId, callback)
    return frameId
  })
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
    frames.delete(id)
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test("scrolls the page continuously while a drag stays near either viewport edge", () => {
  renderHook(() => useDragPageAutoScroll(true))
  dragAt(790)
  nextFrame()
  const first = top
  expect(first).toBeGreaterThan(400)
  nextFrame()
  expect(top).toBeGreaterThan(first)
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top, behavior: "instant" })

  dragAt(10)
  const beforeUp = top
  nextFrame()
  expect(top).toBeLessThan(beforeUp)
})

test("stops in the middle and clamps to the page boundaries without leaving an animation running", () => {
  renderHook(() => useDragPageAutoScroll(true))
  dragAt(790)
  nextFrame()
  const beforeMiddle = top
  dragAt(400)
  nextFrame()
  expect(top).toBe(beforeMiddle)
  expect(frames.size).toBe(0)

  top = 1799
  dragAt(799)
  nextFrame()
  expect(top).toBe(1800)
  nextFrame()
  expect(frames.size).toBe(0)

  top = 1
  dragAt(1)
  nextFrame()
  expect(top).toBe(0)
  nextFrame()
  expect(frames.size).toBe(0)
})

test.each(["drop", "dragend"])(
  "cancels pending scrolling immediately on %s, including drops outside the table",
  (type) => {
    renderHook(() => useDragPageAutoScroll(true))
    dragAt(790)
    expect(frames.size).toBe(1)
    fireEvent(document.body, new Event(type, { bubbles: true }))
    expect(frames.size).toBe(0)
    dragAt(790)
    nextFrame()
    expect(top).toBe(400)
  }
)

test("does not react to unrelated drags and cleans up when disabled or unmounted", () => {
  const view = renderHook(({ active }) => useDragPageAutoScroll(active), {
    initialProps: { active: false },
  })
  dragAt(790)
  expect(frames.size).toBe(0)

  view.rerender({ active: true })
  dragAt(790)
  expect(frames.size).toBe(1)
  view.rerender({ active: false })
  expect(frames.size).toBe(0)
  nextFrame()
  expect(top).toBe(400)

  view.rerender({ active: true })
  dragAt(790)
  view.unmount()
  expect(frames.size).toBe(0)
  dragAt(790)
  expect(frames.size).toBe(0)
})

test("stops when leaving the window and resumes only after a new in-page drag position", () => {
  renderHook(() => useDragPageAutoScroll(true))
  dragAt(790)
  fireEvent(
    document.documentElement,
    new MouseEvent("dragleave", { bubbles: true, relatedTarget: null })
  )
  nextFrame()
  expect(top).toBe(400)
  expect(frames.size).toBe(0)

  dragAt(790)
  nextFrame()
  expect(top).toBeGreaterThan(400)
  fireEvent.blur(window)
  expect(frames.size).toBe(0)
})
