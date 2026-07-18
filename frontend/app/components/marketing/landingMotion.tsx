"use client";

import { useEffect, useRef } from "react";
import {
  animate,
  motion,
  useInView,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";

type LandingSectionMotionOptions = {
  depth?: number;
  scaleRange?: [number, number];
};

export function useLandingSectionMotion<T extends HTMLElement = HTMLElement>(
  options: LandingSectionMotionOptions = {},
) {
  const ref = useRef<T | null>(null);
  const reduceMotion = useReducedMotion();
  const inView = useInView(ref, {
    margin: "-12% 0px -12% 0px",
    amount: 0.15,
  });

  const depth = options.depth ?? 20;
  const scaleRange = options.scaleRange ?? [0.996, 1.004];
  const baseOffset = depth * 0.22;
  const baseScale = scaleRange[0];
  const y = useMotionValue(reduceMotion ? 0 : baseOffset);
  const scale = useMotionValue(reduceMotion ? 1 : baseScale);

  // Animate only when sections enter or leave the viewport instead of tracking every
  // section continuously on scroll. This preserves the floating feel with far less work.
  useEffect(() => {
    if (reduceMotion) {
      y.set(0);
      scale.set(1);
      return;
    }

    const targetY = inView ? 0 : baseOffset;
    const targetScale = inView ? 1 : baseScale;
    const yAnimation = animate(y, targetY, {
      type: "spring",
      stiffness: 90,
      damping: 26,
      mass: 0.9,
    });
    const scaleAnimation = animate(scale, targetScale, {
      type: "spring",
      stiffness: 90,
      damping: 26,
      mass: 0.9,
    });

    return () => {
      yAnimation.stop();
      scaleAnimation.stop();
    };
  }, [baseOffset, baseScale, inView, reduceMotion, scale, y]);

  return {
    ref,
    style: reduceMotion
      ? undefined
      : {
          y,
          scale,
          willChange: "transform",
          transformOrigin: "center top",
        },
  };
}

export function LandingScrollEffects() {
  const reduceMotion = useReducedMotion();
  const { scrollY, scrollYProgress } = useScroll();

  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 44,
    damping: 36,
    mass: 1.05,
  });

  const scrollDirection = useMotionValue(1);
  const directionSpring = useSpring(scrollDirection, {
    stiffness: 96,
    damping: 26,
    mass: 0.9,
  });
  const lastScrollY = useRef(0);

  useMotionValueEvent(scrollY, "change", (current) => {
    const delta = current - lastScrollY.current;
    if (Math.abs(delta) > 0.5) {
      scrollDirection.set(delta > 0 ? 1 : -1);
    }
    lastScrollY.current = current;
  });

  const gridX = useTransform(() => smoothProgress.get() * -18 + directionSpring.get() * 8);
  const gridY = useTransform(() => smoothProgress.get() * 22 + directionSpring.get() * -10);
  const gridScale = useTransform(smoothProgress, [0, 1], [1, 1.03]);

  if (reduceMotion) {
    return null;
  }

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <motion.div
        className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(0,255,163,0.04),transparent_35%)] opacity-70"
        style={{ x: gridX, y: gridY, scale: gridScale }}
      />
    </div>
  );
}
