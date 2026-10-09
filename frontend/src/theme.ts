import { useEffect, useState } from "react";

// "system" follows the operating system; "light"/"dark" are an explicit choice kept in this browser.
export type ThemeChoice = "system" | "light" | "dark";
const KEY = "psa-theme";

export function storedChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system"; // storage blocked: fall back to the OS setting
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && systemPrefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(storedChoice);
  useEffect(() => {
    applyTheme(choice);
    if (choice !== "system" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [choice]);
  const set = (c: ThemeChoice) => {
    try {
      if (c === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, c);
    } catch {
      /* choice still applies for this page view */
    }
    setChoice(c);
  };
  return { choice, set };
}
