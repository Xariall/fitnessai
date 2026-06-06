'use client'

import { useState, useEffect } from 'react'
import { RecordsDashboard } from '@/components/RecordsDashboard'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useTelegramWebApp } from '@/lib/hooks/useTelegramWebApp'
import { fetchRecords, ApiError } from '@/lib/api'
import type { RecordsData } from '@/lib/types'

export default function RecordsPage() {
  const webApp = useTelegramWebApp()
  const [data, setData] = useState<RecordsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = async (userId: number, initData?: string) => {
    try {
      setLoading(true)
      setError(null)
      const records = await fetchRecords(userId, initData)
      setData(records)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Ошибка загрузки данных')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!webApp?.userId) return
    loadData(webApp.userId, webApp.initData)
  }, [webApp?.userId])

  if (loading) return <LoadingSpinner />

  if (error) {
    return (
      <ErrorBanner
        message={error}
        onRetry={webApp?.userId ? () => loadData(webApp.userId, webApp.initData) : undefined}
      />
    )
  }

  if (!data) return <ErrorBanner message="Нет данных" />

  return (
    <RecordsDashboard
      data={data}
      userId={webApp!.userId}
      initData={webApp?.initData}
    />
  )
}
