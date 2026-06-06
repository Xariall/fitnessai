/**
 * Telegram WebApp SDK integration
 */

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        initData: string
        initDataUnsafe: Record<string, unknown>
        ready: () => void
        expand: () => void
        close: () => void
      }
    }
  }
}

export interface TelegramUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  language_code?: string
}

export interface TelegramWebApp {
  userId: number
  user?: TelegramUser
  initData: string
}

export function getTelegramWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null

  try {
    const webApp = window.Telegram?.WebApp
    if (!webApp) return null

    webApp.ready()
    webApp.expand()

    const initDataUnsafe = webApp.initDataUnsafe || {}
    const user = initDataUnsafe.user as TelegramUser | undefined

    if (!user?.id) return null

    return {
      userId: user.id,
      user,
      initData: webApp.initData,
    }
  } catch {
    return null
  }
}
