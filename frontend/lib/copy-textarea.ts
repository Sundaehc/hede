export function selectTextareaText(textarea: HTMLTextAreaElement): boolean {
  if (!textarea.isConnected) return false
  try {
    textarea.focus({ preventScroll: true })
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)
    return true
  } catch {
    return false
  }
}

function copySelection(
  textarea: HTMLTextAreaElement,
  expectedText: string
): boolean {
  if (textarea.value !== expectedText || !selectTextareaText(textarea))
    return false
  try {
    return document.execCommand("copy") === true
  } catch {
    return false
  }
}

export async function copyTextareaText(
  textarea: HTMLTextAreaElement
): Promise<boolean> {
  if (!textarea.isConnected) return false
  const text = textarea.value
  try {
    if (typeof navigator.clipboard?.writeText === "function") {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    return copySelection(textarea, text)
  }
  return copySelection(textarea, text)
}
