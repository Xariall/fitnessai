import type { RecordsData, ExerciseChartPoint } from './types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function apiFetch<T>(url: string, initData?: string): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData
  }

  const response = await fetch(url, { method: 'GET', headers })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail || response.statusText

    if (response.status === 401) {
      throw new ApiError('Нет доступа', 401)
    }
    if (response.status === 404) {
      throw new ApiError('Данные не найдены', 404)
    }
    throw new ApiError(detail, response.status)
  }

  return response.json() as Promise<T>
}

export async function fetchRecords(
  telegramUserId: number,
  initData?: string,
): Promise<RecordsData> {
  return apiFetch<RecordsData>(
    `${API_BASE_URL}/api/records/${telegramUserId}?days=90`,
    initData,
  )
}

export async function fetchExerciseProgression(
  telegramUserId: number,
  exerciseId: string,
  initData?: string,
  signal?: AbortSignal,
): Promise<ExerciseChartPoint[]> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData
  }

  const response = await fetch(
    `${API_BASE_URL}/api/records/${telegramUserId}/exercise/${encodeURIComponent(exerciseId)}?days=365`,
    { method: 'GET', headers, signal },
  )

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(body.detail || response.statusText, response.status)
  }

  return response.json() as Promise<ExerciseChartPoint[]>
}

export { ApiError }
