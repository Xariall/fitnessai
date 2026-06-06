'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

const MUSCLE_COLORS: Record<string, string> = {
  chest: '#ef4444',
  back: '#3b82f6',
  legs: '#10b981',
  shoulders: '#f59e0b',
  arms: '#a855f7',
  core: '#6366f1',
  cardio: '#14b8a6',
  other: '#94a3b8',
}

interface Props {
  data: Array<{
    weekKey: string
    weekStart: string
    byMuscleGroup: Record<string, number>
    total: number
  }>
}

export function VolumeBarChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500">
        No weekly data available
      </div>
    )
  }

  // Get unique muscle groups across all weeks
  const allGroups = new Set<string>()
  for (const week of data) {
    for (const group of Object.keys(week.byMuscleGroup)) {
      allGroups.add(group)
    }
  }

  const chartData = data.map(week => ({
    week: week.weekKey.slice(5), // "2024-W23" → "W23"
    ...week.byMuscleGroup,
  }))

  return (
    <ResponsiveContainer width="100%" height={350}>
      <BarChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="week"
          tick={{ fontSize: 12 }}
          stroke="#94a3b8"
        />
        <YAxis
          tick={{ fontSize: 12 }}
          stroke="#94a3b8"
          label={{ value: 'Volume (kg)', angle: -90, position: 'insideLeft' }}
        />
        <Tooltip
          contentStyle={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            fontSize: '12px',
          }}
          formatter={(value: any) => `${Math.round(value)} kg`}
        />
        <Legend />
        {Array.from(allGroups).map(group => (
          <Bar
            key={group}
            dataKey={group}
            stackId="volume"
            fill={MUSCLE_COLORS[group] || '#94a3b8'}
            name={group}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
