'use client'

import { useState, useEffect } from 'react'
import { ExerciseLineChart } from './ExerciseLineChart'
import { VolumeBarChart } from './VolumeBarChart'
import { RecapTable } from './RecapTable'
import { PersonalRecordsSection } from './PersonalRecordsSection'
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
    <div className="max-w-lg mx-auto p-4 space-y-4 pb-8">
      <div className="text-center pt-2 pb-4">
        <h1 className="text-xl font-bold text-slate-900 mb-0.5">Твои рекорды</h1>
        <p className="text-xs text-slate-400">Личные достижения и прогресс</p>
      </div>

      {/* Section 0: Personal Records */}
      {data.personal_records.length > 0 && (
        <Card>
          <CardHeader className="py-4">
            <h2 className="text-base font-semibold text-slate-900">Топ личных рекордов</h2>
            <p className="text-xs text-slate-400 mt-0.5">За последние 90 дней</p>
          </CardHeader>
          <CardContent className="py-3 px-4">
            <PersonalRecordsSection records={data.personal_records} />
          </CardContent>
        </Card>
      )}

      {/* Section 1: Exercise Progression */}
      <Card>
        <CardHeader className="py-4">
          <div className="flex flex-col gap-2">
            <h2 className="text-base font-semibold text-slate-900">Прогрессия нагрузки</h2>
            {data.exercises.length > 0 ? (
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
            ) : (
              <p className="text-xs text-slate-400">Нет упражнений за этот период</p>
            )}
          </div>
        </CardHeader>
        <CardContent className="px-3 py-3">
          {chartLoading ? (
            <div className="h-56 flex items-center justify-center">
              <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-blue-500" />
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
        <CardHeader className="py-4">
          <h2 className="text-base font-semibold text-slate-900">Недельный объём</h2>
          <p className="text-xs text-slate-400 mt-0.5">Вес × повторения по группам мышц</p>
        </CardHeader>
        <CardContent className="px-3 py-3">
          {data.weekly_volume.length > 0 ? (
            <VolumeBarChart data={data.weekly_volume} />
          ) : (
            <p className="text-center text-slate-400 py-8 text-sm">Нет данных за этот период</p>
          )}
        </CardContent>
      </Card>

      {/* Section 3: 12-Week Recap */}
      <Card>
        <CardHeader className="py-4">
          <h2 className="text-base font-semibold text-slate-900">Итоги за 12 недель</h2>
          <p className="text-xs text-slate-400 mt-0.5">Динамика веса и силового показателя</p>
        </CardHeader>
        <CardContent className="px-3 py-3">
          {data.recap_12w.length > 0 ? (
            <RecapTable rows={data.recap_12w} />
          ) : (
            <p className="text-center text-slate-400 py-8 text-sm">
              Пока мало данных. Продолжай тренироваться!
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
