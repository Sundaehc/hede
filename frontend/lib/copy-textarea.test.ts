import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { copyTextareaText, selectTextareaText } from "@/lib/copy-textarea"

const secret = "hmcp_synthetic-copy-test"
let textarea: HTMLTextAreaElement
let writeText: ReturnType<typeof vi.fn>
let legacyCopy: ReturnType<typeof vi.fn>
const originalClipboard = Object.getOwnPropertyDescriptor(
  navigator,
  "clipboard"
)
const originalExecCommand = Object.getOwnPropertyDescriptor(
  document,
  "execCommand"
)

beforeEach(() => {
  textarea = document.createElement("textarea")
  textarea.value = secret
  textarea.readOnly = true
  document.body.appendChild(textarea)
  writeText = vi.fn().mockResolvedValue(undefined)
  legacyCopy = vi.fn().mockReturnValue(true)
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  })
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: legacyCopy,
  })
})

afterEach(() => {
  textarea.remove()
  if (originalClipboard)
    Object.defineProperty(navigator, "clipboard", originalClipboard)
  else Reflect.deleteProperty(navigator, "clipboard")
  if (originalExecCommand)
    Object.defineProperty(document, "execCommand", originalExecCommand)
  else Reflect.deleteProperty(document, "execCommand")
  vi.restoreAllMocks()
})

describe("copying a displayed textarea", () => {
  it("copies only the text using the available Clipboard API", async () => {
    expect(await copyTextareaText(textarea)).toBe(true)
    expect(writeText).toHaveBeenCalledExactlyOnceWith(secret)
    expect(legacyCopy).not.toHaveBeenCalled()
  })

  it("copies synchronously inside the user action when Clipboard API is absent", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    })
    const result = copyTextareaText(textarea)
    expect(legacyCopy).toHaveBeenCalledExactlyOnceWith("copy")
    expect(document.activeElement).toBe(textarea)
    expect(textarea.selectionStart).toBe(0)
    expect(textarea.selectionEnd).toBe(secret.length)
    expect(await result).toBe(true)
    expect(writeText).not.toHaveBeenCalled()
  })

  it("uses selection copying when writeText is not implemented", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {},
    })
    expect(await copyTextareaText(textarea)).toBe(true)
    expect(legacyCopy).toHaveBeenCalledWith("copy")
  })

  it.each(["reject", "throw"])(
    "falls back when Clipboard API fails (%s)",
    async (failure) => {
      if (failure === "reject") writeText.mockRejectedValue(new Error("denied"))
      else
        writeText.mockImplementation(() => {
          throw new Error("denied")
        })
      legacyCopy.mockImplementation(() => {
        expect(document.activeElement).toBe(textarea)
        expect(
          textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)
        ).toBe(secret)
        return true
      })
      expect(await copyTextareaText(textarea)).toBe(true)
      expect(legacyCopy).toHaveBeenCalledExactlyOnceWith("copy")
    }
  )

  it.each(["false", "throw", "missing"])(
    "keeps text selected without reporting success when fallback fails (%s)",
    async (failure) => {
      writeText.mockRejectedValue(new Error("denied"))
      if (failure === "false") legacyCopy.mockReturnValue(false)
      if (failure === "throw")
        legacyCopy.mockImplementation(() => {
          throw new Error("denied")
        })
      if (failure === "missing")
        Object.defineProperty(document, "execCommand", {
          configurable: true,
          value: undefined,
        })
      expect(await copyTextareaText(textarea)).toBe(false)
      expect(document.activeElement).toBe(textarea)
      expect(textarea.selectionStart).toBe(0)
      expect(textarea.selectionEnd).toBe(secret.length)
    }
  )

  it("selects all text without writing to the clipboard", () => {
    textarea.setSelectionRange(2, 3)
    expect(selectTextareaText(textarea)).toBe(true)
    expect(document.activeElement).toBe(textarea)
    expect(textarea.selectionStart).toBe(0)
    expect(textarea.selectionEnd).toBe(secret.length)
    expect(writeText).not.toHaveBeenCalled()
    expect(legacyCopy).not.toHaveBeenCalled()
  })

  it("does not touch the clipboard when the textarea is no longer displayed", async () => {
    textarea.remove()
    expect(selectTextareaText(textarea)).toBe(false)
    expect(await copyTextareaText(textarea)).toBe(false)
    expect(writeText).not.toHaveBeenCalled()
    expect(legacyCopy).not.toHaveBeenCalled()
  })

  it.each(["removed", "changed"])(
    "does not perform a late fallback after text is %s",
    async (change) => {
      let rejectCopy!: (error: Error) => void
      writeText.mockReturnValue(
        new Promise((_resolve, reject) => {
          rejectCopy = reject
        })
      )
      const result = copyTextareaText(textarea)
      if (change === "removed") textarea.remove()
      else textarea.value = "hmcp_other-synthetic-token"
      rejectCopy(new Error("denied"))
      expect(await result).toBe(false)
      expect(legacyCopy).not.toHaveBeenCalled()
    }
  )

  it("does not copy unrelated selections if selecting the textarea fails", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    })
    vi.spyOn(textarea, "select").mockImplementation(() => {
      throw new Error("selection blocked")
    })
    expect(await copyTextareaText(textarea)).toBe(false)
    expect(legacyCopy).not.toHaveBeenCalled()
  })
})
