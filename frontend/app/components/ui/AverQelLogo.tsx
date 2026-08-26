"use client";

import { motion } from "framer-motion";
import Image from "next/image";
import { BRAND_NAME } from "@/lib/brand";

interface AverQelLogoProps {
  size?: "hero" | "nav" | "footer";
  showWordmark?: boolean;
  disableAnimation?: boolean;
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
}: AverQelLogoProps) {
  const { markSize, text, subtext } = sizeMap[size];
  const isHero = size === "hero";
  const playIntro = !disableAnimation && isHero;

  return (
    <div className={`flex min-w-0 items-center ${showWordmark ? "gap-4" : ""}`}>
      {/* Use the shipped static mark so the complete icon is visible immediately. */}
      <div
        className="relative shrink-0"
        style={{ width: markSize, height: markSize }}
        aria-hidden={showWordmark ? true : undefined}
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
          alt={showWordmark ? "" : BRAND_NAME}
          width={markSize}
          height={markSize}
          priority={isHero}
          className="relative z-10 block h-full w-full object-contain"
        />
      </div>

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
