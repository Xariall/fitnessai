/**
 * API client for Records backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

export async function fetchRecords(telegramUserId: number) {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/records/${telegramUserId}?days=90`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    )

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(
        error.detail ||
        `Failed to fetch records: ${response.statusText}`
      )
    }

    return response.json()
  } catch (error: any) {
    throw new Error(error.message || 'Failed to fetch training records')
  }
}
