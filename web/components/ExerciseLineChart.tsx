'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { ExerciseChartPoint } from '@/lib/types'

interface Props {
  points: ExerciseChartPoint[]
  exerciseName: string
}

export function ExerciseLineChart({ points, exerciseName }: Props) {
  if (points.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
        Выбери упражнение для просмотра прогрессии
      </div>
    )
  }

  if (points.length < 2) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
        Недостаточно данных для графика (нужно минимум 2 тренировки)
      </div>
    )
  }

  const chartData = points.map(p => ({
    date: p.date.slice(5), // "2024-06-05" → "06-05"
    'Макс. вес': p.maxWeight,
    'Расч. 1RM': p.estimated1RM,
    _raw: p,
  }))

  return (
    <div>
      {exerciseName && (
        <p className="text-sm text-slate-600 mb-3">{exerciseName}</p>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11 }}
            stroke="#94a3b8"
          />
          <YAxis
            tick={{ fontSize: 11 }}
            stroke="#94a3b8"
            unit=" кг"
          />
          <Tooltip
            contentStyle={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              fontSize: '12px',
            }}
            formatter={(value: number, name: string) => [`${value} кг`, name]}
            labelFormatter={(label: string) => `Дата: ${label}`}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Line
            type="monotone"
            dataKey="Макс. вес"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
          <Line
            type="monotone"
            dataKey="Расч. 1RM"
            stroke="#ef4444"
            strokeDasharray="4 4"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
