import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { QuestionConfig } from "@/data/onboardingQuestions";
import type { AnswerValue } from "@/types/userProfile";

interface QuestionCardProps {
  question: QuestionConfig;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
  error?: string;
}

export function QuestionCard({
  question,
  value,
  onChange,
  error,
}: QuestionCardProps) {
  const [noneSelected, setNoneSelected] = useState(
    question.type === "none-or-text" && value === "none"
  );

  const inputBase =
    "bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/60 transition-colors w-full";

  // ── text ─────────────────────────────────────────────────────────────────
  if (question.type === "text") {
    return (
      <div className="space-y-2">
        <input
          type="text"
          value={(value as string) ?? ""}
          onChange={e => onChange(e.target.value)}
          placeholder={question.placeholder}
          aria-label={question.question}
          className={inputBase}
          autoFocus
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ── numeric ───────────────────────────────────────────────────────────────
  if (question.type === "numeric") {
    return (
      <div className="space-y-2">
        <input
          type="number"
          value={(value as number) ?? ""}
          onChange={e => {
            const n = e.target.value === "" ? null : Number(e.target.value);
            onChange(n);
          }}
          placeholder={question.placeholder}
          min={question.validation?.min}
          max={question.validation?.max}
          aria-label={question.question}
          className={inputBase}
          autoFocus
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ── single-select ─────────────────────────────────────────────────────────
  if (question.type === "single-select") {
    const cols =
      (question.options?.length ?? 0) <= 3 ? "grid-cols-3" : "grid-cols-2";
    return (
      <div className="space-y-2">
        <div
          className={`grid ${cols} gap-2`}
          role="radiogroup"
          aria-label={question.question}
        >
          {question.options?.map(opt => {
            const active = value === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => onChange(opt.value)}
                className={`p-3 rounded-xl border text-left transition-all duration-200 ${
                  active
                    ? "bg-purple-500/20 border-purple-500/60"
                    : "bg-white/5 border-white/10 hover:border-white/20"
                }`}
              >
                <p className="text-sm font-medium text-white">{opt.label}</p>
                {opt.description && (
                  <p className="text-xs text-white/40 mt-0.5">
                    {opt.description}
                  </p>
                )}
              </button>
            );
          })}
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ── multi-select ──────────────────────────────────────────────────────────
  if (question.type === "multi-select") {
    const selected = (value as string[]) ?? [];
    const toggle = (v: string) => {
      const next = selected.includes(v)
        ? selected.filter(s => s !== v)
        : [...selected, v];
      onChange(next);
    };
    return (
      <div className="space-y-2">
        <div
          className="flex flex-wrap gap-2"
          role="group"
          aria-label={question.question}
        >
          {question.options?.map(opt => {
            const active = selected.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                aria-pressed={active}
                onClick={() => toggle(opt.value)}
                className={`px-4 py-2 rounded-full text-sm font-medium border transition-all duration-200 ${
                  active
                    ? "bg-purple-500/30 border-purple-500/60 text-white"
                    : "bg-white/5 border-white/10 text-white/60 hover:border-white/20 hover:text-white"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ── none-or-text ──────────────────────────────────────────────────────────
  if (question.type === "none-or-text") {
    const handleNone = () => {
      setNoneSelected(true);
      onChange("none");
    };
    const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setNoneSelected(false);
      onChange(e.target.value);
    };

    return (
      <div className="space-y-3">
        <button
          type="button"
          onClick={handleNone}
          aria-pressed={noneSelected}
          className={`w-full py-3 rounded-xl border text-sm font-medium transition-all duration-200 ${
            noneSelected
              ? "bg-purple-500/20 border-purple-500/60 text-white"
              : "bg-white/5 border-white/10 text-white/60 hover:border-white/20 hover:text-white"
          }`}
        >
          Нет / Не знаю
        </button>
        <div className="relative">
          <p className="text-xs text-white/40 mb-1">Или опиши:</p>
          <textarea
            value={noneSelected ? "" : ((value as string) ?? "")}
            onChange={handleTextChange}
            placeholder={question.placeholder}
            rows={3}
            maxLength={2000}
            aria-label={`${question.question} — текстовое поле`}
            className={`${inputBase} resize-none`}
            disabled={noneSelected}
          />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ── numeric-select ────────────────────────────────────────────────────────
  if (question.type === "numeric-select") {
    return (
      <div className="space-y-2">
        <div
          className="flex flex-wrap gap-2"
          role="radiogroup"
          aria-label={question.question}
        >
          {question.options?.map(opt => {
            const active = String(value) === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => onChange(Number(opt.value))}
                className={`w-12 h-12 rounded-xl border text-sm font-medium transition-all duration-200 ${
                  active
                    ? "bg-purple-500/30 border-purple-500/60 text-white"
                    : "bg-white/5 border-white/10 text-white/60 hover:border-white/20 hover:text-white"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  return null;
}
