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
import { MUSCLE_GROUP_LABELS, MUSCLE_GROUP_COLORS, formatVolume } from '@/lib/constants'
import type { WeeklyVolumePoint } from '@/lib/types'

interface Props {
  data: WeeklyVolumePoint[]
}

export function VolumeBarChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
        Нет данных за этот период
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
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="week"
          tick={{ fontSize: 11 }}
          stroke="#94a3b8"
        />
        <YAxis
          tick={{ fontSize: 11 }}
          stroke="#94a3b8"
        />
        <Tooltip
          contentStyle={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            fontSize: '12px',
          }}
          formatter={(value: number, name: string) => [
            formatVolume(value),
            MUSCLE_GROUP_LABELS[name] || name,
          ]}
        />
        <Legend
          formatter={(value: string) => MUSCLE_GROUP_LABELS[value] || value}
          wrapperStyle={{ fontSize: '12px' }}
        />
        {Array.from(allGroups).map(group => (
          <Bar
            key={group}
            dataKey={group}
            stackId="volume"
            fill={MUSCLE_GROUP_COLORS[group] || '#94a3b8'}
            name={group}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
