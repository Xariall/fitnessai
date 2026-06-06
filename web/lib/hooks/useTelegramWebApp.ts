'use client'

import { useState, useEffect } from 'react'
import { getTelegramWebApp, TelegramWebApp } from '../telegram'

export function useTelegramWebApp(): TelegramWebApp | null {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null)

  useEffect(() => {
    // Small delay to ensure Telegram SDK is loaded
    const timer = setTimeout(() => {
      const app = getTelegramWebApp()
      setWebApp(app)

      if (!app) {
        console.warn('Telegram WebApp not available (may be in web view)')
      }
    }, 100)

    return () => clearTimeout(timer)
  }, [])

  return webApp
}
