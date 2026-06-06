'use client'

import { useState, useMemo } from 'react'
import { ExerciseLineChart } from './ExerciseLineChart'
import { VolumeBarChart } from './VolumeBarChart'
import { RecapTable } from './RecapTable'
import { Card, CardContent, CardHeader } from './ui/Card'
import { Select } from './ui/Select'

interface Props {
  data: {
    max_lifts: any[]
    weekly_volume: any[]
    recap_12w: any[]
  }
}

export function RecordsDashboard({ data }: Props) {
  const [selectedExerciseId, setSelectedExerciseId] = useState<string | undefined>()

  // Prepare unique exercises for dropdown
  const exercises = useMemo(() => {
    const unique = new Map<string, any>()
    for (const lift of data.max_lifts) {
      unique.set(lift.exercise_id, {
        id: lift.exercise_id,
        name: lift.name,
        name_ru: lift.name_ru,
      })
    }
    return Array.from(unique.values())
  }, [data.max_lifts])

  // Set default selection
  const defaultExerciseId = selectedExerciseId || exercises[0]?.id
  const selectedExercise = exercises.find(e => e.id === defaultExerciseId)

  // Get all data points for selected exercise
  const selectedPoints = data.max_lifts.filter(
    lift => lift.exercise_id === defaultExerciseId
  )

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">💪 Your Training Records</h1>
        <p className="text-slate-600">Track your progression over time</p>
      </div>

      {/* Section 1: Max Load & 1RM */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4">
            <h2 className="text-xl font-semibold text-slate-900">Max Load & Estimated 1RM</h2>
            {exercises.length > 0 && (
              <Select
                value={defaultExerciseId || ''}
                onChange={(e) => setSelectedExerciseId(e.target.value)}
              >
                <option value="">Select an exercise...</option>
                {exercises.map(ex => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name_ru || ex.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {selectedPoints.length > 0 && selectedExercise ? (
            <ExerciseLineChart points={selectedPoints} exercise={selectedExercise} />
          ) : (
            <p className="text-center text-slate-500 py-8">
              Select an exercise to view progression
            </p>
          )}
        </CardContent>
      </Card>

      {/* Section 2: Weekly Volume */}
      <Card>
        <CardHeader>
          <h2 className="text-xl font-semibold text-slate-900">Weekly Volume by Muscle Group</h2>
          <p className="text-sm text-slate-600">Volume = weight × reps (working sets only)</p>
        </CardHeader>
        <CardContent>
          {data.weekly_volume.length > 0 ? (
            <VolumeBarChart data={data.weekly_volume} />
          ) : (
            <p className="text-center text-slate-500 py-8">No weekly data available</p>
          )}
        </CardContent>
      </Card>

      {/* Section 3: 12-Week Recap */}
      <Card>
        <CardHeader>
          <h2 className="text-xl font-semibold text-slate-900">12-Week Recap</h2>
        </CardHeader>
        <CardContent>
          {data.recap_12w.length > 0 ? (
            <RecapTable rows={data.recap_12w} />
          ) : (
            <p className="text-center text-slate-500 py-8">
              Not enough data yet. Keep training! 💪
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
