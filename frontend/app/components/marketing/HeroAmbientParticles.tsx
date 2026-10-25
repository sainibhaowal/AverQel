"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";

type AmbientParticle = {
  x: number;
  y: number;
  radius: number;
  phase: number;
  speed: number;
  drift: number;
  opacity: number;
  color: string;
};

const PARTICLE_COLORS = ["0, 255, 163", "0, 184, 255", "214, 239, 244"] as const;

export default function HeroAmbientParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    let width = 0;
    let height = 0;
    let time = 0;
    let frame = 0;
    let isVisible = !document.hidden;
    let isInViewport = true;
    const particles: AmbientParticle[] = [];

    const draw = () => {
      context.clearRect(0, 0, width, height);

      for (const particle of particles) {
        const drift = reduceMotion ? 0 : Math.sin(time * particle.speed + particle.phase);
        const twinkle = reduceMotion
          ? 0.72
          : 0.52 + Math.sin(time * particle.speed * 1.8 + particle.phase) * 0.18;

        context.beginPath();
        context.arc(
          particle.x + drift * particle.drift,
          particle.y + drift * particle.drift * 0.55,
          particle.radius,
          0,
          Math.PI * 2,
        );
        context.fillStyle = `rgba(${particle.color}, ${particle.opacity * twinkle})`;
        context.fill();
      }
    };

    const resize = () => {
      const parent = canvas.parentElement;
      width = parent?.clientWidth ?? window.innerWidth;
      height = parent?.clientHeight ?? window.innerHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.max(1, Math.floor(width * ratio));
      canvas.height = Math.max(1, Math.floor(height * ratio));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);

      const count = Math.max(90, Math.min(260, Math.round(width / 5.5)));
      particles.length = 0;
      for (let index = 0; index < count; index += 1) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          radius: 0.55 + Math.random() * 1.35,
          phase: Math.random() * Math.PI * 2,
          speed: 0.25 + Math.random() * 0.55,
          drift: 2 + Math.random() * 8,
          opacity: 0.16 + Math.random() * 0.28,
          color: PARTICLE_COLORS[Math.floor(Math.random() * PARTICLE_COLORS.length)],
        });
      }

      draw();
    };

    const render = () => {
      frame = 0;
      if (!isVisible || !isInViewport) return;

      time += 0.012;
      draw();
      if (!reduceMotion) frame = window.requestAnimationFrame(render);
    };

    const scheduleRender = () => {
      if (reduceMotion) {
        draw();
      } else if (isVisible && isInViewport && !frame) {
        frame = window.requestAnimationFrame(render);
      }
    };

    const handleVisibilityChange = () => {
      isVisible = !document.hidden;
      if (!isVisible && frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
      } else {
        scheduleRender();
      }
    };

    const observer = new IntersectionObserver(([entry]) => {
      isInViewport = entry?.isIntersecting ?? true;
      if (!isInViewport && frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
      } else {
        scheduleRender();
      }
    });

    resize();
    observer.observe(canvas);
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    scheduleRender();

    return () => {
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, [reduceMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      data-hero-ambient-particles
      className="pointer-events-none absolute inset-0 z-0 h-full w-full"
    />
  );
}
