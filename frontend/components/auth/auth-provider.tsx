"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"

import { getCurrentUser, logout as logoutRequest } from "@/lib/api"
import type { AuthUser } from "@/lib/types"


type AuthContextValue = {
  user: AuthUser | null
  loading: boolean
  refresh: () => Promise<void>
  setUser: (user: AuthUser | null) => void
  logout: () => Promise<void>
  hasPermission: (permission: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)


export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshTokenRef = useRef(0)

  const refresh = useCallback(async () => {
    const refreshToken = refreshTokenRef.current + 1
    refreshTokenRef.current = refreshToken
    setLoading(true)
    try {
      const response = await getCurrentUser()
      if (refreshTokenRef.current === refreshToken) {
        setUser(response.user)
      }
    } catch {
      if (refreshTokenRef.current === refreshToken) {
        setUser(null)
      }
    } finally {
      if (refreshTokenRef.current === refreshToken) {
        setLoading(false)
      }
    }
  }, [])

  const setAuthenticatedUser = useCallback((nextUser: AuthUser | null) => {
    refreshTokenRef.current += 1
    setUser(nextUser)
    setLoading(false)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setAuthenticatedUser(null)
    }
  }, [setAuthenticatedUser])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    refresh,
    setUser: setAuthenticatedUser,
    logout,
    hasPermission: (permission: string) => {
      const permissions = user?.permissions ?? []
      return permissions.includes("*") || permissions.includes(permission)
    },
  }), [loading, logout, refresh, setAuthenticatedUser, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}


export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return context
}
