import type { Metadata } from 'next'
import Script from 'next/script'
import '../styles/globals.css'

export const metadata: Metadata = {
  title: 'FitnessAI — Рекорды',
  description: 'Тренировочные рекорды и прогресс',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <head>
        <Script
          src="https://telegram.org/js/telegram-web-app.js"
          strategy="beforeInteractive"
        />
      </head>
      <body className="bg-slate-50 text-slate-900">
        <div className="min-h-screen">
          {children}
        </div>
      </body>
    </html>
  )
}
