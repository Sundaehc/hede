import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"

afterEach(cleanup)

test.each([4350, 43500, 435000])(
  "keeps long page numbers content-sized at the last page %i",
  (lastPage) => {
    render(
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationLink href="?page=1">1</PaginationLink>
          </PaginationItem>
          <PaginationItem>
            <PaginationEllipsis />
          </PaginationItem>
          <PaginationItem>
            <PaginationLink href={`?page=${lastPage - 1}`}>
              {lastPage - 1}
            </PaginationLink>
          </PaginationItem>
          <PaginationItem>
            <PaginationLink href={`?page=${lastPage}`} isActive>
              {lastPage}
            </PaginationLink>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    )

    const links = screen.getAllByRole("link")
    for (const link of links) {
      expect(link).toHaveAttribute("data-size", "default")
      expect(link).toHaveClass("min-w-8", "px-2.5", "tabular-nums")
      expect(link).not.toHaveClass("size-8", "w-8")
      expect(link.parentElement).toHaveClass("shrink-0")
    }
    expect(
      screen.getByRole("link", { name: String(lastPage) })
    ).toHaveAttribute("aria-current", "page")
    expect(
      screen.getByRole("link", { name: String(lastPage - 1) })
    ).not.toHaveAttribute("aria-current")
    expect(screen.getByText("More pages").parentElement).toHaveAttribute(
      "aria-hidden",
      "true"
    )
  }
)

test("wraps page items on narrow layouts without shrinking their labels", () => {
  render(
    <Pagination>
      <PaginationContent>
        {[1, 434999, 435000, 435001, 900000].map((page) => (
          <PaginationItem key={page}>
            <PaginationLink href={`?page=${page}`}>{page}</PaginationLink>
          </PaginationItem>
        ))}
      </PaginationContent>
    </Pagination>
  )

  const navigation = screen.getByRole("navigation")
  expect(navigation).toHaveClass("max-w-full")
  expect(within(navigation).getByRole("list")).toHaveClass(
    "max-w-full",
    "flex-wrap",
    "justify-center",
    "gap-1"
  )
  for (const item of screen.getAllByRole("listitem")) {
    expect(item).toHaveClass("shrink-0")
  }
})

test("keeps caller layout and button-size overrides", () => {
  render(
    <Pagination className="mx-0 w-auto">
      <PaginationContent className="justify-end">
        <PaginationItem className="shrink">
          <PaginationLink href="?page=2" className="px-4" size="lg">
            2
          </PaginationLink>
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )

  expect(screen.getByRole("navigation")).toHaveClass("mx-0", "w-auto")
  expect(screen.getByRole("navigation")).not.toHaveClass("mx-auto", "w-full")
  expect(screen.getByRole("list")).toHaveClass("justify-end")
  expect(screen.getByRole("listitem")).not.toHaveClass("shrink-0")
  expect(screen.getByRole("link")).toHaveAttribute("data-size", "lg")
  expect(screen.getByRole("link")).toHaveClass("px-4")
  expect(screen.getByRole("link")).not.toHaveClass("px-2.5")
})

test("preserves page, previous and next click handlers and compact labels", async () => {
  const user = userEvent.setup()
  const previousClick = vi.fn()
  const nextClick = vi.fn()
  const pageClick = vi.fn()
  render(
    <Pagination>
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious text="上一页" onClick={previousClick} />
        </PaginationItem>
        <PaginationItem>
          <PaginationLink onClick={pageClick}>4349</PaginationLink>
        </PaginationItem>
        <PaginationItem>
          <PaginationNext text="下一页" onClick={nextClick} />
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )

  await user.click(screen.getByLabelText("Go to previous page"))
  await user.click(screen.getByText("4349"))
  await user.click(screen.getByLabelText("Go to next page"))

  expect(previousClick).toHaveBeenCalledOnce()
  expect(pageClick).toHaveBeenCalledOnce()
  expect(nextClick).toHaveBeenCalledOnce()
  expect(screen.getByText("上一页")).toHaveClass("hidden", "sm:block")
  expect(screen.getByText("下一页")).toHaveClass("hidden", "sm:block")
})
