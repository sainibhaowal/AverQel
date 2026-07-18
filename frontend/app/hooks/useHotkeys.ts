"use client";

import { useEffect } from "react";

type KeyCombo = {
  key: string;
  ctrlOrCmd?: boolean;
};

export function useHotkeys(combos: { combo: KeyCombo; handler: (e: KeyboardEvent) => void }[]) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      for (const { combo, handler } of combos) {
        const keyMatch = e.key.toLowerCase() === combo.key.toLowerCase();
        const modifierMatch = combo.ctrlOrCmd ? e.ctrlKey || e.metaKey : true;

        if (keyMatch && modifierMatch) {
          e.preventDefault();
          handler(e);
          return; // Stop after first match
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [combos]);
}
