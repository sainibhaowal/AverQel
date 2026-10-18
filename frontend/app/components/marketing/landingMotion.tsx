"use client";

import { useRef, useSyncExternalStore } from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

type LandingSectionMotionOptions = {
  depth?: number;
  scaleRange?: [number, number];
};

const subscribeToElectronRuntime = () => () => undefined;
const getElectronRuntimeSnapshot = () => typeof window !== "undefined" && Boolean(window.electron);
const getServerElectronRuntimeSnapshot = () => false;

export function useLandingSectionMotion<T extends HTMLElement = HTMLElement>(
  options: LandingSectionMotionOptions = {},
) {
  const ref = useRef<T | null>(null);
  const reduceMotion = useReducedMotion();
  const isElectron = useSyncExternalStore(
    subscribeToElectronRuntime,
    getElectronRuntimeSnapshot,
    getServerElectronRuntimeSnapshot,
  );
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    mass: 0.45,
    restDelta: 0.001,
  });

  const depth = options.depth ?? 14;
  const scaleRange = options.scaleRange ?? [0.996, 1.004];
  const minScale = Math.min(...scaleRange);
  const maxScale = Math.max(...scaleRange);
  const y = useTransform(smoothProgress, [0, 0.5, 1], [depth * 0.55, 0, -depth * 0.55]);
  const scale = useTransform(smoothProgress, [0, 0.5, 1], [minScale, maxScale, minScale]);
  const motionDisabled = Boolean(reduceMotion || isElectron);

  return {
    ref,
    style: motionDisabled
      ? undefined
      : {
          y,
          scale,
          willChange: "transform" as const,
          transformOrigin: "center top" as const,
        },
  };
}

export function LandingAmbientEffects() {
  const reduceMotion = useReducedMotion();
  const isElectron = useSyncExternalStore(
    subscribeToElectronRuntime,
    getElectronRuntimeSnapshot,
    getServerElectronRuntimeSnapshot,
  );
  const { scrollYProgress } = useScroll();
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 90,
    damping: 32,
    mass: 0.55,
    restDelta: 0.001,
  });
  const x = useTransform(smoothProgress, [0, 1], [0, -20]);
  const y = useTransform(smoothProgress, [0, 1], [0, 28]);
  const scale = useTransform(smoothProgress, [0, 0.5, 1], [1, 1.018, 1]);
  const motionDisabled = Boolean(reduceMotion || isElectron);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <motion.div
        className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(0,255,163,0.04),transparent_35%)] opacity-70"
        style={motionDisabled ? undefined : { x, y, scale }}
        animate={motionDisabled ? undefined : { opacity: [0.28, 0.48, 0.28] }}
        transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
