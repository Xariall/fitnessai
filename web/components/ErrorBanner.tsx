'use client'

interface Props {
  message: string
  onRetry?: () => void
}

export function ErrorBanner({ message, onRetry }: Props) {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-50 p-4">
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-sm text-center">
        <h2 className="text-base font-semibold text-red-900 mb-2">Ошибка</h2>
        <p className="text-sm text-red-700">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 px-4 py-2 bg-red-600 text-white text-sm rounded-md hover:bg-red-700 transition-colors"
          >
            Попробовать снова
          </button>
        )}
      </div>
    </div>
  )
}
