"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Theme = "light" | "dark" | "system";
const OPTIONS: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

function apply(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTheme((localStorage.getItem("lta-theme") as Theme) ?? "system");
  }, []);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem("lta-theme", theme);
    apply(theme);
  }, [theme, mounted]);

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-full border border-hairline bg-surface/60 p-0.5"
    >
      {OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          role="radio"
          aria-checked={mounted && theme === value}
          aria-label={`${label} theme`}
          onClick={() => setTheme(value)}
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-full transition",
            mounted && theme === value
              ? "bg-brand-500/15 text-brand-600 dark:text-brand-300"
              : "text-muted hover:text-primary",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden />
        </button>
      ))}
    </div>
  );
}
