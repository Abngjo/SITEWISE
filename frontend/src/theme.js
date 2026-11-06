import { useEffect, useState } from "react";

// Theme: "system" | "light" | "dark". Resolved value is written to <html data-theme>.
export function useTheme() {
  const [pref, setPref] = useState(() => { try { return localStorage.getItem("sw-theme") || "system"; } catch { return "system"; } });
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: light)");
    const apply = () => {
      const t = pref === "system" ? (mq.matches ? "light" : "dark") : pref;
      document.documentElement.dataset.theme = t;
    };
    apply();
    try { localStorage.setItem("sw-theme", pref); } catch { /* storage blocked */ }
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [pref]);
  return [pref, setPref];
}
