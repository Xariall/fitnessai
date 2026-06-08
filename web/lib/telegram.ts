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

/**
 * Apply Telegram theme colors to CSS custom properties.
 * Call once after WebApp is initialized to get native Telegram feel.
 */
export function applyTelegramTheme(): void {
  if (typeof window === 'undefined') return

  try {
    const themeParams = (window.Telegram?.WebApp as Record<string, unknown>)?.themeParams as Record<string, string> | undefined
    if (!themeParams) return

    const mappings: Record<string, string> = {
      bg_color: '--tg-theme-bg-color',
      text_color: '--tg-theme-text-color',
      hint_color: '--tg-theme-hint-color',
      link_color: '--tg-theme-link-color',
      button_color: '--tg-theme-button-color',
      button_text_color: '--tg-theme-button-text-color',
      secondary_bg_color: '--tg-theme-secondary-bg-color',
    }

    for (const [key, cssVar] of Object.entries(mappings)) {
      const value = themeParams[key]
      if (value) {
        document.documentElement.style.setProperty(cssVar, value)
      }
    }
  } catch {
    // Ignore errors — theme is a progressive enhancement
  }
}
