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

interface Point {
  date: string
  weight_kg: number
  estimated_1rm: number
}

interface Props {
  points: Point[]
  exercise: {
    name: string
    name_ru: string
  }
}

export function ExerciseLineChart({ points, exercise }: Props) {
  if (points.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500">
        No data available
      </div>
    )
  }

  const chartData = points.map(p => ({
    date: p.date,
    'Max Weight (kg)': p.weight_kg,
    'Est. 1RM (kg)': p.estimated_1rm,
  }))

  return (
    <div>
      <h3 className="text-sm text-slate-600 mb-4">
        {exercise.name_ru || exercise.name}
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            stroke="#94a3b8"
          />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="#94a3b8"
          />
          <Tooltip
            contentStyle={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '6px',
              fontSize: '12px',
            }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="Max Weight (kg)"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
          <Line
            type="monotone"
            dataKey="Est. 1RM (kg)"
            stroke="#ef4444"
            strokeDasharray="4 4"
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
