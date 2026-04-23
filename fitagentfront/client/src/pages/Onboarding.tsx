import { useEffect } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/_core/hooks/useAuth";
import { OnboardingFlow } from "@/components/Onboarding/OnboardingFlow";

export default function Onboarding() {
  const { user, loading } = useAuth();
  const [, navigate] = useLocation();

  useEffect(() => {
    if (!loading && !user) navigate("/");
  }, [loading, user, navigate]);

  if (loading || !user) return null;

  return (
    <div className="min-h-screen bg-gradient-dark relative overflow-hidden flex flex-col items-center justify-center px-4 py-12">
      {/* Background orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-gradient-to-br from-purple-600 to-purple-800 rounded-full blur-3xl opacity-10 animate-float" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-gradient-to-br from-cyan-500 to-purple-600 rounded-full blur-3xl opacity-10 animate-float-reverse" />
      </div>

      <div className="relative z-10 w-full max-w-lg">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10 justify-center">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-purple-500/50">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 20v-8M6 20v-4M18 20v-12" />
            </svg>
          </div>
          <span className="text-xl font-bold text-white">FitAgent</span>
        </div>

        <OnboardingFlow initialName={user.name ?? undefined} />
      </div>
    </div>
  );
}
