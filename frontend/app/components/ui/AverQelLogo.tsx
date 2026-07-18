"use client";

import { motion } from "framer-motion";
import { BRAND_NAME } from "@/lib/brand";

interface AverQelLogoProps {
  size?: "hero" | "nav" | "footer";
  showWordmark?: boolean;
  disableAnimation?: boolean;
}

const sizeMap = {
  hero: { scale: 1, text: "text-4xl", subtext: true },
  nav: { scale: 0.45, text: "text-xl", subtext: false },
  footer: { scale: 0.35, text: "text-lg", subtext: false },
};

export default function AverQelLogo({
  size = "hero",
  showWordmark = true,
  disableAnimation = false,
}: AverQelLogoProps) {
  const { scale, text, subtext } = sizeMap[size];
  const isHero = size === "hero";
  const playIntro = !disableAnimation && isHero;

  return (
    <div className={`flex items-center ${showWordmark ? "gap-4" : ""}`}>
      {/* Logo Mark */}
      <motion.div
        className="relative"
        style={{ width: 80 * scale, height: 80 * scale }}
        initial={playIntro ? { opacity: 0, scale: 0.8 } : false}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Ambient glow behind mark */}
        <motion.div
          className="absolute inset-[-30%] rounded-full blur-2xl"
          style={{
            background:
              "radial-gradient(circle, rgba(59,130,246,0.25) 0%, rgba(6,182,212,0.1) 50%, transparent 80%)",
          }}
          initial={false}
          animate={!disableAnimation && isHero ? { opacity: [0.5, 0.8, 0.5] } : { opacity: 0.45 }}
          transition={
            !disableAnimation && isHero
              ? { duration: 4, repeat: Infinity, ease: "easeInOut" }
              : { duration: 0.2 }
          }
        />

        <svg
          viewBox="0 0 80 80"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="relative z-10 h-full w-full"
        >
          <defs>
            <linearGradient id="markGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="50%" stopColor="#06b6d4" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
            <linearGradient id="markGrad2" x1="100%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#06b6d4" />
              <stop offset="100%" stopColor="#3b82f6" />
            </linearGradient>
            <linearGradient id="shieldFill" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="0%" stopColor="rgba(59,130,246,0.15)" />
              <stop offset="100%" stopColor="rgba(139,92,246,0.05)" />
            </linearGradient>
          </defs>

          {/* Shield / Document shape - solid and bold */}
          <motion.path
            d="M16 8 L56 8 L64 16 L64 62 C64 66 61 70 57 72 L40 78 L23 72 C19 70 16 66 16 62 Z"
            fill="url(#shieldFill)"
            stroke="url(#markGrad)"
            strokeWidth="2.5"
            strokeLinejoin="round"
            initial={playIntro ? { pathLength: 0, fillOpacity: 0 } : false}
            animate={{ pathLength: 1, fillOpacity: 1 }}
            transition={{ duration: 1.5, ease: "easeInOut" }}
          />

          {/* Document fold corner */}
          <motion.path
            d="M56 8 L56 16 L64 16"
            stroke="url(#markGrad2)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
            initial={playIntro ? { pathLength: 0 } : false}
            animate={{ pathLength: 1 }}
            transition={{ delay: 0.8, duration: 0.6 }}
          />
          <motion.path
            d="M56 8 L64 16 L56 16 Z"
            fill="rgba(6,182,212,0.1)"
            initial={playIntro ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.2, duration: 0.4 }}
          />

          {/* Bold D letterform - thick and geometric */}
          <motion.path
            d="M30 28 L30 54 L42 54 C51 54 54 48 54 41 C54 34 51 28 42 28 Z"
            fill="none"
            stroke="url(#markGrad)"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={playIntro ? { pathLength: 0 } : false}
            animate={{ pathLength: 1 }}
            transition={{ delay: 0.5, duration: 1.2, ease: "easeInOut" }}
          />

          {/* Inner D fill with subtle gradient */}
          <motion.path
            d="M33 31 L33 51 L41 51 C48 51 51 46.5 51 41 C51 35.5 48 31 41 31 Z"
            fill="url(#markGrad)"
            fillOpacity={0.12}
            initial={playIntro ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.5, duration: 0.6 }}
          />

          {/* Search/intelligence accent - small lens at bottom right of D */}
          <motion.circle
            cx={50}
            cy={48}
            r={5}
            fill="none"
            stroke="var(--accent-cyan)"
            strokeWidth="2"
            initial={playIntro ? { scale: 0, opacity: 0 } : false}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 1.6, duration: 0.4, type: "spring", stiffness: 300 }}
            style={{ transformOrigin: "50px 48px" }}
          />
          <motion.line
            x1="54"
            y1="52"
            x2="58"
            y2="56"
            stroke="var(--accent-cyan)"
            strokeWidth="2.5"
            strokeLinecap="round"
            initial={playIntro ? { pathLength: 0 } : false}
            animate={{ pathLength: 1 }}
            transition={{ delay: 1.8, duration: 0.3 }}
          />

          {/* Subtle pulse ring */}
          <motion.circle
            cx={40}
            cy={42}
            r={30}
            fill="none"
            stroke="url(#markGrad)"
            strokeWidth="0.5"
            initial={false}
            animate={
              !disableAnimation && isHero
                ? { scale: [0.93, 1.06, 0.93], opacity: [0.1, 0.2, 0.1] }
                : { scale: 1, opacity: 0.08 }
            }
            transition={
              !disableAnimation && isHero
                ? { duration: 4, repeat: Infinity, ease: "easeInOut" }
                : { duration: 0.2 }
            }
            style={{ transformOrigin: "40px 42px" }}
          />
        </svg>
      </motion.div>

      {/* Wordmark */}
      {showWordmark && (
        <div className="flex flex-col">
          <motion.span
            className={`${text} gradient-text leading-none font-bold tracking-tight`}
            initial={playIntro ? { opacity: 0, x: -12 } : false}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            {BRAND_NAME}
          </motion.span>
          {subtext && (
            <motion.span
              className="mt-1 text-xs tracking-[0.25em] text-slate-500 uppercase"
              initial={playIntro ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.0, duration: 0.8 }}
            >
              Document Intelligence
            </motion.span>
          )}
        </div>
      )}
    </div>
  );
}
