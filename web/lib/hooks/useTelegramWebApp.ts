'use client'

import { useState, useEffect } from 'react'
import { getTelegramWebApp, applyTelegramTheme, TelegramWebApp } from '../telegram'

const DEV_USER_ID = process.env.NEXT_PUBLIC_DEV_USER_ID

export function useTelegramWebApp(): TelegramWebApp | null {
  const [webApp, setWebApp] = useState<TelegramWebApp | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      const app = getTelegramWebApp()

      if (app) {
        applyTelegramTheme()
        setWebApp(app)
        return
      }

      // Dev fallback: use env variable for testing outside Telegram
      if (DEV_USER_ID) {
        setWebApp({
          userId: Number(DEV_USER_ID),
          initData: '',
        })
      }
    }, 100)

    return () => clearTimeout(timer)
  }, [])

  return webApp
}
