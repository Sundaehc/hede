import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import LoginPage from "@/app/login/page"

const { mockLogin, mockReplace, mockSetUser } = vi.hoisted(() => ({
  mockLogin: vi.fn(),
  mockReplace: vi.fn(),
  mockSetUser: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ setUser: mockSetUser }),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return { ...actual, login: mockLogin }
})

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLogin.mockResolvedValue({
      user: { id: 1, username: "15858703012", permissions: [] },
      message: "登录成功",
    })
  })

  it("submits values written directly by a browser password manager", async () => {
    render(<LoginPage />)
    const username = screen.getByLabelText("账号") as HTMLInputElement
    const password = screen.getByLabelText("密码") as HTMLInputElement
    const form = screen.getByRole("button", { name: "登录" }).closest("form")

    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(username, " 15858703012 ")
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(password, " edge-autofilled-password ")
    fireEvent.submit(form!)

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        username: "15858703012",
        password: "edge-autofilled-password",
      })
    })
    expect(mockSetUser).toHaveBeenCalled()
    expect(mockReplace).toHaveBeenCalledWith("/products")
  })
})
