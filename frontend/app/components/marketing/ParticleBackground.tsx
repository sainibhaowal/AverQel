"use client";

import { useEffect, useRef, useCallback } from "react";

/**
 * DeepSpace Kinetic Field - KINETIC EDITION
 * The "Sweet Spot" between high-excitement and enterprise-grade maturity.
 * - Fluid Bezier Mesh: A 3D-warping field of intelligence.
 * - Prismatic Signal Flux: Data "sparkles" that travel along the warped lattice.
 * - Magnetic Inertia: The field physically bends around user presence.
 * - Deep Optical Depth: Multi-layered refraction and soft-glow bokehs.
 */

export default function ParticleBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: -1000, y: -1000, active: false });

  const handleMouseMove = useCallback((e: MouseEvent) => {
    mouseRef.current = { x: e.clientX, y: e.clientY, active: true };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    let animationId: number;
    let cw = 0,
      ch = 0;
    let time = 0;

    const resize = () => {
      cw = canvas.width = window.innerWidth;
      ch = canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", handleMouseMove);

    // Lattice Grid Points
    const rows = 18;
    const cols = 24;
    const points: { x: number; y: number; bx: number; by: number; vz: number }[] = [];

    for (let r = 0; r <= rows; r++) {
      for (let c = 0; c <= cols; c++) {
        points.push({
          x: 0,
          y: 0,
          bx: c / cols,
          by: r / rows,
          vz: Math.random() * Math.PI * 2,
        });
      }
    }

    const signals: { r: number; c: number; progress: number; speed: number; color: string }[] = [];

    const animate = () => {
      time += 0.005;
      ctx.fillStyle = "#020617";
      ctx.fillRect(0, 0, cw, ch);

      // 1. Draw Deep Radiant Bokehs
      const bokehs = [
        {
          x: 0.5 + Math.sin(time * 0.3) * 0.2,
          y: 0.4 + Math.cos(time * 0.2) * 0.1,
          r: 0.6,
          c: "rgba(59, 130, 246, 0.08)",
        },
        {
          x: 0.3 + Math.cos(time * 0.4) * 0.1,
          y: 0.7 + Math.sin(time * 0.3) * 0.2,
          r: 0.4,
          c: "rgba(139, 92, 246, 0.06)",
        },
      ];
      bokehs.forEach((b) => {
        const g = ctx.createRadialGradient(b.x * cw, b.y * ch, 0, b.x * cw, b.y * ch, b.r * cw);
        g.addColorStop(0, b.c);
        g.addColorStop(1, "rgba(2, 6, 23, 0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, cw, ch);
      });

      // 2. Update Lattice Points (Magnetic Warp)
      points.forEach((p) => {
        const base_x = p.bx * cw;
        const base_y = p.by * ch;

        // Organic ripple
        const ripple = Math.sin(time + p.bx * 5 + p.by * 3) * 15;

        // Mouse warp
        let mx = base_x,
          my = base_y;
        if (mouseRef.current.active) {
          const dx = mouseRef.current.x - base_x;
          const dy = mouseRef.current.y - base_y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 400) {
            const force = (1 - dist / 400) * 60;
            mx -= (dx / dist) * force;
            my -= (dy / dist) * force;
          }
        }

        p.x = mx;
        p.y = my + ripple;
      });

      // 3. Render Kinetic Lattice (Bezier Curves)
      ctx.beginPath();
      ctx.lineWidth = 1;
      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const i = r * (cols + 1) + c;
          const p = points[i];

          // Horizontal lines
          if (c < cols) {
            const next = points[i + 1];
            ctx.moveTo(p.x, p.y);
            ctx.bezierCurveTo(
              p.x + (next.x - p.x) / 2,
              p.y,
              p.x + (next.x - p.x) / 2,
              next.y,
              next.x,
              next.y,
            );
          }
          // Vertical lines
          if (r < rows) {
            const next = points[i + (cols + 1)];
            ctx.moveTo(p.x, p.y);
            ctx.bezierCurveTo(
              p.x,
              p.y + (next.y - p.y) / 2,
              next.x,
              p.y + (next.y - p.y) / 2,
              next.x,
              next.y,
            );
          }
        }
      }
      ctx.strokeStyle = "rgba(59, 130, 246, 0.06)";
      ctx.stroke();

      // 4. Prismatic Signal Flux
      if (Math.random() < 0.1) {
        signals.push({
          r: Math.floor(Math.random() * rows),
          c: Math.floor(Math.random() * cols),
          progress: 0,
          speed: 0.005 + Math.random() * 0.01,
          color: Math.random() > 0.5 ? "59, 130, 246" : "139, 92, 246",
        });
      }

      signals.forEach((s, i) => {
        s.progress += s.speed;
        if (s.progress >= 1) {
          signals.splice(i, 1);
          return;
        }

        const idx = s.r * (cols + 1) + s.c;
        const p1 = points[idx];
        const p2 = points[idx + 1];
        if (!p2) return;

        const sx = p1.x + (p2.x - p1.x) * s.progress;
        const sy = p1.y + (p2.y - p1.y) * s.progress;
        const alpha = Math.sin(s.progress * Math.PI);

        ctx.beginPath();
        ctx.arc(sx, sy, 1.5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${s.color}, ${alpha * 0.8})`;
        ctx.fill();

        // Prismatic Glow
        const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, 15);
        g.addColorStop(0, `rgba(${s.color}, ${alpha * 0.3})`);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(sx - 15, sy - 15, 30, 30);
      });

      // 5. Fine Premium Grain
      ctx.fillStyle = "rgba(255, 255, 255, 0.012)";
      for (let i = 0; i < 800; i++) {
        ctx.fillRect(Math.random() * cw, Math.random() * ch, 1, 1);
      }

      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, [handleMouseMove]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-0" />;
}
