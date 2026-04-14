import { useState } from "react";
import { X, Sparkles } from "lucide-react";

interface Props {
  date: string;
  open: boolean;
  onClose: () => void;
  onGenerate: (notes: string) => void;
  isLoading: boolean;
}

export default function RegeneratePlanModal({ date, open, onClose, onGenerate, isLoading }: Props) {
  const [notes, setNotes] = useState("");

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onGenerate(notes);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-md glass p-6 rounded-2xl border border-white/10 animate-slide-in-up">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-bold text-white">Сгенерировать план</h2>
            <p className="text-xs text-white/40 mt-0.5">{date}</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-all"
          >
            <X size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-2">
              Пожелания <span className="text-white/30">(необязательно)</span>
            </label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Например: без глютена, больше белка, бюджетные продукты..."
              rows={4}
              maxLength={1000}
              disabled={isLoading}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors resize-none text-sm"
            />
            <p className="text-right text-[11px] text-white/20 mt-1">{notes.length}/1000</p>
          </div>

          <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-xs text-purple-300">
            AI составит полноценный план на день с учётом вашей нормы КБЖУ и пожеланий.
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Генерирую план...
              </>
            ) : (
              <>
                <Sparkles size={16} />
                Сгенерировать план
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
