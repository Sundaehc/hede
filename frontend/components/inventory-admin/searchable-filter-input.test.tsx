import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { SearchableFilterInput } from "@/components/inventory-admin/searchable-filter-input"

describe("SearchableFilterInput", () => {
  it("submits on Enter even when only one option matches", async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    const handleSubmit = vi.fn()

    render(
      <SearchableFilterInput
        value="千百度供应商"
        options={[{ value: "千百度供应商", label: "千百度供应商" }]}
        onChange={handleChange}
        onSubmit={handleSubmit}
      />,
    )

    await user.click(screen.getByRole("combobox"))
    await user.keyboard("{Enter}")

    expect(handleSubmit).toHaveBeenCalledOnce()
    expect(handleChange).not.toHaveBeenCalled()
  })
})
