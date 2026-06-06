'use client'

import { useState, useEffect } from 'react'
import { RecordsDashboard } from '@/components/RecordsDashboard'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useTelegramWebApp } from '@/lib/hooks/useTelegramWebApp'
import { fetchRecords } from '@/lib/api'

export default function RecordsPage() {
  const webApp = useTelegramWebApp()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!webApp?.userId) return

    const loadData = async () => {
      try {
        setLoading(true)
        setError(null)
        const records = await fetchRecords(webApp.userId)
        setData(records)
      } catch (err: any) {
        setError(err.message || 'Failed to load records')
      } finally {
        setLoading(false)
      }
    }

    // Small delay to ensure Telegram SDK is ready
    const timer = setTimeout(loadData, 500)
    return () => clearTimeout(timer)
  }, [webApp?.userId])

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return <ErrorBanner message="No data received" />

  return <RecordsDashboard data={data} />
}
