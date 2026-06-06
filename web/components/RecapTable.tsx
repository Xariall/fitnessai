'use client'

interface Row {
  exerciseName: string
  muscleGroup: string
  sessions: number
  firstWeight: number
  firstDate: string
  lastWeight: number
  lastDate: string
  weightDelta: number
  firstE1RM: number
  lastE1RM: number
  e1rmDelta: number
}

interface Props {
  rows: Row[]
}

function deltaColor(value: number): string {
  if (value > 0) return 'text-emerald-600 font-medium'
  if (value < 0) return 'text-rose-600 font-medium'
  return 'text-slate-500'
}

function formatDelta(value: number): string {
  if (value > 0) return `+${value.toFixed(1)}`
  return value.toFixed(1)
}

export function RecapTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <div className="text-center text-slate-500 py-8">
        Not enough data for comparison
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b-2 border-slate-300">
            <th className="px-4 py-3 text-left font-semibold text-slate-900">Exercise</th>
            <th className="px-4 py-3 text-center font-semibold text-slate-900">Sessions</th>
            <th className="px-4 py-3 text-center font-semibold text-slate-900">Start → End</th>
            <th className="px-4 py-3 text-center font-semibold text-slate-900">Δ Weight</th>
            <th className="px-4 py-3 text-center font-semibold text-slate-900">Δ 1RM</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={idx}
              className="border-b border-slate-200 hover:bg-slate-50"
            >
              <td className="px-4 py-3">
                <div className="font-medium text-slate-900">{row.exerciseName}</div>
                <div className="text-xs text-slate-500">{row.muscleGroup}</div>
              </td>
              <td className="px-4 py-3 text-center text-slate-700">
                {row.sessions}
              </td>
              <td className="px-4 py-3 text-center text-slate-700">
                <div className="text-sm">
                  {row.firstWeight} → {row.lastWeight} kg
                </div>
                <div className="text-xs text-slate-500">
                  ({row.firstDate} → {row.lastDate})
                </div>
              </td>
              <td className={`px-4 py-3 text-center ${deltaColor(row.weightDelta)}`}>
                {formatDelta(row.weightDelta)} kg
              </td>
              <td className={`px-4 py-3 text-center ${deltaColor(row.e1rmDelta)}`}>
                {formatDelta(row.e1rmDelta)} kg
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
