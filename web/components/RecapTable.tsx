'use client'

import { MUSCLE_GROUP_LABELS } from '@/lib/constants'
import type { RecapRow } from '@/lib/types'

interface Props {
  rows: RecapRow[]
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
      <div className="text-center text-slate-400 text-sm py-8">
        Недостаточно данных для сравнения
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b-2 border-slate-300">
            <th className="px-3 py-2 text-left font-semibold text-slate-900">Упражнение</th>
            <th className="px-3 py-2 text-center font-semibold text-slate-900">Сессий</th>
            <th className="px-3 py-2 text-center font-semibold text-slate-900">Старт → Финиш</th>
            <th className="px-3 py-2 text-center font-semibold text-slate-900">Δ Вес</th>
            <th className="px-3 py-2 text-center font-semibold text-slate-900">Δ 1RM</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.exercise_id}
              className="border-b border-slate-200 hover:bg-slate-50"
            >
              <td className="px-3 py-2">
                <div className="font-medium text-slate-900 text-sm">{row.exerciseName}</div>
                <div className="text-xs text-slate-400">
                  {MUSCLE_GROUP_LABELS[row.muscleGroup] || row.muscleGroup}
                </div>
              </td>
              <td className="px-3 py-2 text-center text-slate-700">
                {row.sessions}
              </td>
              <td className="px-3 py-2 text-center text-slate-700">
                <div className="text-sm">
                  {row.firstWeight} → {row.lastWeight} кг
                </div>
              </td>
              <td className={`px-3 py-2 text-center ${deltaColor(row.weightDelta)}`}>
                {formatDelta(row.weightDelta)}
              </td>
              <td className={`px-3 py-2 text-center ${deltaColor(row.e1rmDelta)}`}>
                {formatDelta(row.e1rmDelta)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
