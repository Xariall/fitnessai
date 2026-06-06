# FitnessAI Records Web App

Telegram Web App for viewing training records, max lifts, and progression charts.

## Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup

```bash
npm install
```

### Run

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Environment Variables

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8001
```

For production, use your deployed backend URL.

## Building

```bash
npm run build
npm start
```

## Deployment

### Vercel

1. Push code to GitHub
2. Import project in Vercel
3. Set environment variables:
   - `NEXT_PUBLIC_API_URL` → your backend URL
4. Deploy

## How It Works

1. **Telegram Web App Initialization**: The app reads `tgWebAppInitData` from Telegram SDK
2. **Authentication**: Telegram User ID is extracted and sent to backend
3. **Data Fetch**: Backend returns:
   - **Max Lifts**: Top exercises by estimated 1RM (last 90 days)
   - **Weekly Volume**: Aggregated volume by muscle group per ISO week
   - **12-Week Recap**: First vs last session comparison per exercise
4. **Visualization**:
   - **LineChart**: Max weight + estimated 1RM trend
   - **BarChart**: Weekly volume stacked by muscle group
   - **Table**: 12-week progress with deltas

## Components

- `RecordsDashboard` - Main orchestrator
- `ExerciseLineChart` - Max load progression
- `VolumeBarChart` - Weekly volume by muscle group
- `RecapTable` - 12-week comparison table
- `LoadingSpinner` - Loading state
- `ErrorBanner` - Error state

## Data Flow

```
Telegram WebApp
    ↓
User ID extracted from tgWebAppInitData
    ↓
GET /api/records/{telegram_user_id}
    ↓
Backend aggregates Supabase data:
  • workout_logs (90 days)
  • users (bodyweight)
  • exercise_db (classification)
    ↓
Frontend renders charts/tables
```

## Notes

- **Bodyweight Exercises**: Effective weight = bodyweight + added_kg
- **1RM Calculation**: Epley formula: weight × (1 + reps/30)
- **Weekly Aggregation**: Volume = weight × reps per muscle group
- **Muscle Groups**: Classified from exercise names using keyword matching
