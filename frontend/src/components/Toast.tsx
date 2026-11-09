// Toast notifications: short messages that slide in at the bottom and fade away.

import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { cn } from "./ui";

type Tone = "success" | "info" | "error";
type Toast = { id: number; tone: Tone; message: string };

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  const icon = { success: CheckCircle2, info: Info, error: TriangleAlert };

  return (
    <ToastContext.Provider value={push}>
      {children}
      {/* aria-live: screen readers announce each toast as it appears. */}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 lg:bottom-6">
        <AnimatePresence>
          {toasts.map((t) => {
            const Icon = icon[t.tone];
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: 16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.96 }}
                className="panel pointer-events-auto flex max-w-sm items-center gap-3 rounded-xl px-4 py-3 text-sm shadow-lg"
                role="status"
              >
                <Icon
                  className={cn("h-5 w-5 shrink-0", t.tone === "success" && "text-ok", t.tone === "info" && "text-primary", t.tone === "error" && "text-bad")}
                  aria-hidden
                />
                {t.message}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
