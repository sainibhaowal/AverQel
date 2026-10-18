"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import { BRAND_NAME } from "@/lib/brand";
import AverQelWordmark from "./AverQelWordmark";

interface AverQelLogoProps {
  size?: "hero" | "nav" | "footer";
  showWordmark?: boolean;
  disableAnimation?: boolean;
  animateWordmark?: boolean;
  wordmarkVisible?: boolean;
}

const sizeMap = {
  hero: {
    markWidth: 128,
    markHeight: 64,
    wordmarkSize: "hero" as const,
    maxWordmarkWidth: 284,
    gap: "0rem",
    subtext: true,
  },
  nav: {
    markWidth: 92,
    markHeight: 46,
    wordmarkSize: "nav" as const,
    maxWordmarkWidth: 172,
    gap: "0rem",
    subtext: false,
  },
  footer: {
    markWidth: 58,
    markHeight: 30,
    wordmarkSize: "footer" as const,
    maxWordmarkWidth: 120,
    gap: "0rem",
    subtext: false,
  },
};

export default function AverQelLogo({
  size = "hero",
  showWordmark = true,
  disableAnimation = false,
  animateWordmark = false,
  wordmarkVisible,
}: AverQelLogoProps) {
  const { markWidth, markHeight, wordmarkSize, maxWordmarkWidth, gap, subtext } = sizeMap[size];
  const isHero = size === "hero";
  const playIntro = !disableAnimation && isHero;
  const isWordmarkVisible = wordmarkVisible ?? showWordmark;
  const keepWordmarkMounted = showWordmark || animateWordmark;
  const canAnimateWordmark = animateWordmark;

  return (
    <motion.div
      className={`averqel-logo averqel-logo--${size} flex min-w-0 items-center`}
      data-brand-lockup
      style={{ columnGap: isWordmarkVisible ? gap : "0rem" }}
      initial={false}
      animate={canAnimateWordmark ? { columnGap: isWordmarkVisible ? gap : "0rem" } : undefined}
      transition={
        canAnimateWordmark ? { duration: 0.2, ease: [0.22, 1, 0.36, 1] } : { duration: 0 }
      }
      // The dashboard sidebar is already resizing. Layout projection here
      // causes a second measurement pass for the logo during collapse.
      layout={false}
    >
      {/* Use the shipped static mark so the complete icon is visible immediately. */}
      <motion.div
        className="relative shrink-0"
        style={{ width: markWidth, height: markHeight }}
        aria-hidden={isWordmarkVisible ? true : undefined}
        layout={false}
      >
        {isHero && (
          <div
            className="absolute inset-[-30%] rounded-full blur-2xl"
            style={{
              background:
                "radial-gradient(circle, rgba(59,130,246,0.25) 0%, rgba(6,182,212,0.1) 50%, transparent 80%)",
            }}
          />
        )}
        <Image
          src="/brand/AverQel_Icon.svg"
          alt={isWordmarkVisible ? "" : BRAND_NAME}
          width={markWidth}
          height={markHeight}
          priority
          className={`averqel-logo__mark-image relative z-10 block h-full w-full object-contain ${size === "nav" ? "averqel-logo__mark-image--nav" : ""}`}
        />
      </motion.div>

      {/* Wordmark */}
      {keepWordmarkMounted && (
        <motion.div
          initial={false}
          animate={
            canAnimateWordmark
              ? {
                  maxWidth: isWordmarkVisible ? maxWordmarkWidth : 0,
                  opacity: isWordmarkVisible ? 1 : 0,
                  x: isWordmarkVisible ? 0 : -8,
                }
              : {
                  maxWidth: isWordmarkVisible ? maxWordmarkWidth : 0,
                  opacity: isWordmarkVisible ? 1 : 0,
                  x: 0,
                }
          }
          transition={
            canAnimateWordmark ? { duration: 0.2, ease: [0.22, 1, 0.36, 1] } : { duration: 0 }
          }
          className="averqel-logo__wordmark flex min-w-0 flex-col overflow-hidden"
          aria-hidden={!isWordmarkVisible}
        >
          <motion.div
            className="flex items-center leading-none"
            initial={playIntro ? { opacity: 0, x: -12 } : false}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <AverQelWordmark size={wordmarkSize} />
          </motion.div>
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
        </motion.div>
      )}
    </motion.div>
  );
}
