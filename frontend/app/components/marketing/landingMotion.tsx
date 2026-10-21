"use client";

import { useRef, useSyncExternalStore } from "react";
import { useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

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
