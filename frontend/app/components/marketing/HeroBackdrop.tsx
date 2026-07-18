"use client";

import { motion, useReducedMotion } from "framer-motion";

export default function HeroBackdrop() {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = !reduceMotion;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden bg-[#030508]"
    >
      <motion.div
        className="absolute inset-0 bg-[radial-gradient(circle_at_50%_15%,rgba(0,255,163,0.08),transparent_28%),radial-gradient(circle_at_85%_18%,rgba(0,184,255,0.08),transparent_26%)] opacity-80"
        animate={shouldAnimate ? { x: [0, 4, 0], y: [0, -3, 0] } : { opacity: 0.55 }}
        transition={
          shouldAnimate ? { duration: 18, repeat: Infinity, ease: "easeInOut" } : { duration: 0 }
        }
      />
    </div>
  );
}
