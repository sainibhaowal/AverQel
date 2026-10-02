"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import { BRAND_NAME } from "@/lib/brand";

interface AverQelLogoProps {
  size?: "hero" | "nav" | "footer";
  showWordmark?: boolean;
  disableAnimation?: boolean;
  animateWordmark?: boolean;
  wordmarkVisible?: boolean;
}

const sizeMap = {
  hero: { markSize: 80, text: "text-4xl", subtext: true },
  nav: { markSize: 36, text: "text-xl", subtext: false },
  footer: { markSize: 32, text: "text-lg", subtext: false },
};

export default function AverQelLogo({
  size = "hero",
  showWordmark = true,
  disableAnimation = false,
  animateWordmark = false,
  wordmarkVisible,
}: AverQelLogoProps) {
  const { markSize, text, subtext } = sizeMap[size];
  const isHero = size === "hero";
  const playIntro = !disableAnimation && isHero;
  const isWordmarkVisible = wordmarkVisible ?? showWordmark;
  const keepWordmarkMounted = showWordmark || animateWordmark;
  const canAnimateWordmark = animateWordmark;

  return (
    <motion.div
      className={`flex min-w-0 items-center ${canAnimateWordmark || !showWordmark ? "" : "gap-4"}`}
      initial={false}
      animate={canAnimateWordmark ? { columnGap: isWordmarkVisible ? "1rem" : "0rem" } : undefined}
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
        style={{ width: markSize, height: markSize }}
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
          src="/logo_icon.png"
          alt={isWordmarkVisible ? "" : BRAND_NAME}
          width={markSize}
          height={markSize}
          priority={isHero}
          className="relative z-10 block h-full w-full object-contain"
        />
      </motion.div>

      {/* Wordmark */}
      {keepWordmarkMounted && (
        <motion.div
          initial={false}
          animate={
            canAnimateWordmark
              ? {
                  maxWidth: isWordmarkVisible ? 180 : 0,
                  opacity: isWordmarkVisible ? 1 : 0,
                  x: isWordmarkVisible ? 0 : -8,
                }
              : {
                  maxWidth: isWordmarkVisible ? 180 : 0,
                  opacity: isWordmarkVisible ? 1 : 0,
                  x: 0,
                }
          }
          transition={
            canAnimateWordmark ? { duration: 0.2, ease: [0.22, 1, 0.36, 1] } : { duration: 0 }
          }
          className="flex min-w-0 flex-col overflow-hidden"
          aria-hidden={!isWordmarkVisible}
        >
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
        </motion.div>
      )}
    </motion.div>
  );
}
