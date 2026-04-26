import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

function renderTabs() {
  render(
    <Tabs defaultValue="tab-1">
      <TabsList>
        <TabsTrigger value="tab-1">Tab 1</TabsTrigger>
        <TabsTrigger value="tab-2">Tab 2</TabsTrigger>
        <TabsTrigger value="tab-3">Tab 3</TabsTrigger>
      </TabsList>
      <TabsContent value="tab-1">Panel 1</TabsContent>
      <TabsContent value="tab-2">Panel 2</TabsContent>
      <TabsContent value="tab-3">Panel 3</TabsContent>
    </Tabs>
  )

  return {
    tab1: screen.getByRole("tab", { name: "Tab 1" }),
    tab2: screen.getByRole("tab", { name: "Tab 2" }),
    tab3: screen.getByRole("tab", { name: "Tab 3" }),
  }
}

describe("Tabs", () => {
  it("renders the default selected tab and panel", () => {
    const { tab1, tab2, tab3 } = renderTabs()

    expect(tab1).toHaveAttribute("aria-selected", "true")
    expect(tab1).toHaveAttribute("tabindex", "0")
    expect(tab2).toHaveAttribute("aria-selected", "false")
    expect(tab3).toHaveAttribute("aria-selected", "false")
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel 1")
  })

  it("moves focus and selection with ArrowRight in horizontal tabs", () => {
    const { tab1, tab2 } = renderTabs()

    tab1.focus()
    fireEvent.keyDown(tab1, { key: "ArrowRight" })

    expect(tab2).toHaveFocus()
    expect(tab2).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel 2")
  })

  it("moves to the first and last tab with Home and End", () => {
    const { tab1, tab2, tab3 } = renderTabs()

    tab2.focus()
    fireEvent.keyDown(tab2, { key: "End" })

    expect(tab3).toHaveFocus()
    expect(tab3).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel 3")

    fireEvent.keyDown(tab3, { key: "Home" })

    expect(tab1).toHaveFocus()
    expect(tab1).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel 1")
  })
})
