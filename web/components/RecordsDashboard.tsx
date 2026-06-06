'use client'

import { useState, useEffect } from 'react'
import { ExerciseLineChart } from './ExerciseLineChart'
import { VolumeBarChart } from './VolumeBarChart'
import { RecapTable } from './RecapTable'
import { Card, CardContent, CardHeader } from './ui/Card'
import { Select } from './ui/Select'
import { fetchExerciseProgression } from '@/lib/api'
import type { RecordsData, ExerciseChartPoint } from '@/lib/types'

interface Props {
  data: RecordsData
  userId: number
  initData?: string
}

export function RecordsDashboard({ data, userId, initData }: Props) {
  const [selectedExerciseId, setSelectedExerciseId] = useState<string>('')
  const [chartPoints, setChartPoints] = useState<ExerciseChartPoint[]>([])
  const [chartLoading, setChartLoading] = useState(false)

  // Set default exercise
  useEffect(() => {
    if (data.exercises.length > 0 && !selectedExerciseId) {
      setSelectedExerciseId(data.exercises[0].id)
    }
  }, [data.exercises, selectedExerciseId])

  // Fetch exercise progression with AbortController
  useEffect(() => {
    if (!selectedExerciseId) return

    const controller = new AbortController()
    setChartLoading(true)

    fetchExerciseProgression(userId, selectedExerciseId, initData, controller.signal)
      .then((points) => {
        if (!controller.signal.aborted) {
          setChartPoints(points)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setChartPoints([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setChartLoading(false)
        }
      })

    return () => controller.abort()
  }, [selectedExerciseId, userId, initData])

  const selectedExercise = data.exercises.find(e => e.id === selectedExerciseId)

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Твои рекорды</h1>
        <p className="text-sm text-slate-500">Отслеживай прогресс</p>
      </div>

      {/* Section 1: Exercise Progression */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Прогрессия нагрузки</h2>
            {data.exercises.length > 0 && (
              <Select
                value={selectedExerciseId}
                onChange={(e) => setSelectedExerciseId(e.target.value)}
              >
                {data.exercises.map(ex => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name_ru || ex.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {chartLoading ? (
            <div className="h-64 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            </div>
          ) : (
            <ExerciseLineChart
              points={chartPoints}
              exerciseName={selectedExercise?.name_ru || selectedExercise?.name || ''}
            />
          )}
        </CardContent>
      </Card>

      {/* Section 2: Weekly Volume */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-slate-900">Недельный объём по группам мышц</h2>
          <p className="text-xs text-slate-500">Объём = вес × повторения (рабочие подходы)</p>
        </CardHeader>
        <CardContent>
          {data.weekly_volume.length > 0 ? (
            <VolumeBarChart data={data.weekly_volume} />
          ) : (
            <p className="text-center text-slate-500 py-8">Нет данных за этот период</p>
          )}
        </CardContent>
      </Card>

      {/* Section 3: 12-Week Recap */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-slate-900">Итоги за 12 недель</h2>
        </CardHeader>
        <CardContent>
          {data.recap_12w.length > 0 ? (
            <RecapTable rows={data.recap_12w} />
          ) : (
            <p className="text-center text-slate-500 py-8">
              Пока мало данных. Продолжай тренироваться!
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
