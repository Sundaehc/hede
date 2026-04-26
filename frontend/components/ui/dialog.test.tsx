import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

function renderDialog() {
  render(
    <Dialog>
      <DialogTrigger>Open dialog</DialogTrigger>
      <DialogContent>
        <DialogTitle>Dialog title</DialogTitle>
        <DialogDescription>Dialog description</DialogDescription>
        <DialogClose>Close dialog</DialogClose>
      </DialogContent>
    </Dialog>
  )

  return {
    trigger: screen.getByRole("button", { name: "Open dialog" }),
  }
}

describe("Dialog", () => {
  it("opens when the trigger is clicked", async () => {
    const user = userEvent.setup()
    const { trigger } = renderDialog()

    await user.click(trigger)

    expect(screen.getByRole("dialog", { name: "Dialog title" })).toBeInTheDocument()
  })

  it("closes on Escape", async () => {
    const user = userEvent.setup()
    const { trigger } = renderDialog()

    await user.click(trigger)

    const dialog = screen.getByRole("dialog", { name: "Dialog title" })
    fireEvent.keyDown(dialog, { key: "Escape" })

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Dialog title" })).not.toBeInTheDocument()
    })
  })

  it("returns focus to the trigger after close", async () => {
    const user = userEvent.setup()
    const { trigger } = renderDialog()

    await user.click(trigger)

    const dialog = screen.getByRole("dialog", { name: "Dialog title" })
    fireEvent.keyDown(dialog, { key: "Escape" })

    await waitFor(() => {
      expect(trigger).toHaveFocus()
    })
  })
})
