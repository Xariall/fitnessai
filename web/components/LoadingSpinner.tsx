'use client'

export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-50">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500" />
        <p className="mt-4 text-sm text-slate-500">Загружаю твои рекорды...</p>
      </div>
    </div>
  )
}
