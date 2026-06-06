export interface PersonalRecord {
  exercise_id: string
  name: string
  name_ru: string
  muscleGroup: string
  weight_kg: number
  reps_done: number
  effective_weight: number
  estimated_1rm: number
  date: string
}

export interface ExerciseChartPoint {
  date: string
  maxWeight: number
  topSetReps: number
  estimated1RM: number
  totalVolume: number
  exerciseName: string
  nameRu: string
}

export interface WeeklyVolumePoint {
  weekKey: string
  weekStart: string
  byMuscleGroup: Record<string, number>
  total: number
}

export interface RecapRow {
  exercise_id: string
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

export interface ExerciseInfo {
  id: string
  name: string
  name_ru: string
  muscleGroup: string
}

export interface RecordsData {
  exercises: ExerciseInfo[]
  personal_records: PersonalRecord[]
  weekly_volume: WeeklyVolumePoint[]
  recap_12w: RecapRow[]
}
