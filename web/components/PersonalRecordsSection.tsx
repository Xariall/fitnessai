'use client'

import { MUSCLE_GROUP_LABELS, MUSCLE_GROUP_COLORS } from '@/lib/constants'
import type { PersonalRecord } from '@/lib/types'

interface Props {
  records: PersonalRecord[]
}

const MEDALS = ['🥇', '🥈', '🥉']

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export function PersonalRecordsSection({ records }: Props) {
  if (records.length === 0) {
    return (
      <div className="text-center text-slate-400 text-sm py-8">
        Пока нет данных о рекордах. Начни тренироваться!
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {records.map((record, idx) => {
        const medal = MEDALS[idx] ?? `${idx + 1}.`
        const groupLabel = MUSCLE_GROUP_LABELS[record.muscleGroup] || record.muscleGroup
        const groupColor = MUSCLE_GROUP_COLORS[record.muscleGroup] || '#94a3b8'

        return (
          <div
            key={record.exercise_id}
            className="flex items-center gap-3 py-3 px-1 border-b border-slate-100 last:border-0"
          >
            <span className="text-xl w-7 shrink-0 text-center">{medal}</span>

            <div className="flex-1 min-w-0">
              <div className="font-medium text-slate-900 text-sm truncate">
                {record.name_ru || record.name}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span
                  className="text-xs px-1.5 py-0.5 rounded-full text-white font-medium"
                  style={{ backgroundColor: groupColor }}
                >
                  {groupLabel}
                </span>
                <span className="text-xs text-slate-400">{formatDate(record.date)}</span>
              </div>
            </div>

            <div className="text-right shrink-0">
              <div className="text-base font-bold text-slate-900">
                {record.effective_weight} <span className="text-xs font-normal text-slate-500">кг</span>
              </div>
              <div className="text-xs text-slate-400">
                {record.reps_done} повт · 1RM {record.estimated_1rm} кг
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
