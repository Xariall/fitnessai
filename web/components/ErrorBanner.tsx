'use client'

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-50 p-4">
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md text-center">
        <h2 className="text-lg font-semibold text-red-900 mb-2">Error</h2>
        <p className="text-red-700">{message}</p>
        <p className="text-sm text-red-600 mt-4">
          Please try again or contact support.
        </p>
      </div>
    </div>
  )
}
