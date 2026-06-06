export const MUSCLE_GROUP_LABELS: Record<string, string> = {
  chest: 'Грудь',
  back: 'Спина',
  shoulders: 'Плечи',
  biceps: 'Бицепс',
  triceps: 'Трицепс',
  legs: 'Ноги',
  core: 'Пресс',
  arms: 'Руки',
  cardio: 'Кардио',
  other: 'Другое',
}

export const MUSCLE_GROUP_COLORS: Record<string, string> = {
  chest: '#3B82F6',
  back: '#10B981',
  shoulders: '#F59E0B',
  biceps: '#8B5CF6',
  triceps: '#EC4899',
  legs: '#06B6D4',
  core: '#6366F1',
  arms: '#A855F7',
  cardio: '#14B8A6',
  other: '#94A3B8',
}

export function formatVolume(value: number): string {
  return `${Math.round(value).toLocaleString('ru-RU')} кг`
}
