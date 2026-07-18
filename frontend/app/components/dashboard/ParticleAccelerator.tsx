"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "../../context/ThemeContext";

interface OrganicParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  hue: number;
  alpha: number;
  phase: number;
  phaseSpeed: number;
}

interface CloudBlob {
  xFactor: number; // base position as fraction of width
  yFactor: number; // base position as fraction of height
  radiusFactor: number; // base radius as fraction of width
  speedX: number;
  speedY: number;
  offsetX: number;
  offsetY: number;
  rgb: [number, number, number];
  alphaMax: number;
}

export default function ParticleAccelerator() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let particles: OrganicParticle[] = [];
    let clouds: CloudBlob[] = [];
    const particleCount = 200;
    let time = 0;

    // Mouse tracking
    const mouse = { x: 0, y: 0, active: false, targetX: 0, targetY: 0 };
    let clickPulse = 0;

    const initScene = () => {
      const w = canvas.width || 1200;
      const h = canvas.height || 250;

      // 1. Initialize organic matter particles
      particles = [];
      for (let i = 0; i < particleCount; i++) {
        // Distribute standard and hub sizes
        const isHub = i < 15;
        const radius = isHub
          ? 3.0 + Math.random() * 2.5   // Glowing hubs
          : 1.0 + Math.random() * 1.2;  // Small dust particles

        const roll = Math.random();
        const hue = roll < 0.65
          ? 120 + Math.random() * 32   // Vibrant space green (120..152)
          : 215 + Math.random() * 20;  // Deep space blue (215..235)

        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.4,
          vy: (Math.random() - 0.5) * 0.4,
          radius,
          baseRadius: radius,
          hue,
          alpha: 0.35 + Math.random() * 0.55,
          phase: Math.random() * Math.PI * 2,
          phaseSpeed: 0.01 + Math.random() * 0.015,
        });
      }

      // 2. Initialize dynamic RGB gradient cloud blobs (Deep Space Blue/Green vs Soft Pastel Mint/Sky)
      const isDark = theme === "dark";
      clouds = [
        {
          xFactor: 0.2,
          yFactor: 0.4,
          radiusFactor: 0.38,
          speedX: 0.22,
          speedY: 0.18,
          offsetX: Math.random() * 10,
          offsetY: Math.random() * 10,
          rgb: isDark ? [15, 78, 54] : [186, 242, 222], // Dark Forest Green vs Soft Mint Green
          alphaMax: isDark ? 0.26 : 0.22,
        },
        {
          xFactor: 0.5,
          yFactor: 0.6,
          radiusFactor: 0.44,
          speedX: -0.16,
          speedY: 0.24,
          offsetX: Math.random() * 10,
          offsetY: Math.random() * 10,
          rgb: isDark ? [16, 44, 87] : [200, 235, 254], // Deep Space Blue vs Soft Sky Blue
          alphaMax: isDark ? 0.24 : 0.20,
        },
        {
          xFactor: 0.78,
          yFactor: 0.35,
          radiusFactor: 0.4,
          speedX: 0.18,
          speedY: -0.22,
          offsetX: Math.random() * 10,
          offsetY: Math.random() * 10,
          rgb: isDark ? [15, 118, 110] : [214, 251, 245], // Deep Blueish-Green vs Soft Pale Teal
          alphaMax: isDark ? 0.24 : 0.20,
        },
        {
          xFactor: 0.45,
          yFactor: 0.3,
          radiusFactor: 0.32,
          speedX: 0.25,
          speedY: -0.15,
          offsetX: Math.random() * 10,
          offsetY: Math.random() * 10,
          rgb: isDark ? [34, 139, 34] : [225, 253, 236], // Forest Green vs Soft Pastel Green
          alphaMax: isDark ? 0.2 : 0.16,
        },
      ];
    };

    const resizeCanvas = () => {
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      if (w > 0 && h > 0 && (canvas.width !== w || canvas.height !== h)) {
        canvas.width = w;
        canvas.height = h;
        initScene();
      } else if (clouds.length === 0 && w > 0 && h > 0) {
        initScene();
      }
    };

    const parent = canvas.parentElement;

    const handleMouseMove = (e: MouseEvent) => {
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      mouse.targetX = e.clientX - rect.left;
      mouse.targetY = e.clientY - rect.top;
      mouse.active = true;
    };

    const handleMouseLeave = () => {
      mouse.active = false;
    };

    const handleMouseClick = () => {
      clickPulse = 1.0;
    };

    if (parent) {
      parent.addEventListener("mousemove", handleMouseMove);
      parent.addEventListener("mouseleave", handleMouseLeave);
      parent.addEventListener("click", handleMouseClick);
    }

    const animate = () => {
      resizeCanvas();
      const w = canvas.width;
      const h = canvas.height;

      // Use clearRect to maintain transparency so page backgrounds show through
      ctx.clearRect(0, 0, w, h);

      time += 0.008;

      if (clickPulse > 0) {
        clickPulse -= 0.015;
        if (clickPulse < 0) clickPulse = 0;
      }

      // Smooth mouse easing
      mouse.x += (mouse.targetX - mouse.x) * 0.12;
      mouse.y += (mouse.targetY - mouse.y) * 0.12;

      // -----------------------------------------------------------------
      // 1. Draw the organic RGB Gradient Clouds (Nebula Gas)
      // -----------------------------------------------------------------
      ctx.save();
      // Screen blending for dark mode, standard source-over for clean light mode washes
      ctx.globalCompositeOperation = theme === "dark" ? "screen" : "source-over";

      clouds.forEach((c) => {
        // Move cloud center slowly over time
        const cx = c.xFactor * w + Math.sin(time * c.speedX + c.offsetX) * (w * 0.08);
        const cy = c.yFactor * h + Math.cos(time * c.speedY + c.offsetY) * (h * 0.12);
        
        // Dynamic swelling radius
        let rad = c.radiusFactor * w + Math.sin(time * 0.8 + c.offsetX) * 25;
        if (rad < 150) rad = 150;

        // Apply mouse gravity push
        let finalX = cx;
        let finalY = cy;
        if (mouse.active) {
          const dx = mouse.x - cx;
          const dy = mouse.y - cy;
          const dist = Math.hypot(dx, dy);
          if (dist < 220) {
            const pull = (220 - dist) / 220;
            // Clouds warp slowly away from or toward mouse
            finalX += dx * pull * 0.15;
            finalY += dy * pull * 0.15;
            rad += clickPulse * 60;
          }
        }

        // Draw radial gradient gas blob
        const grad = ctx.createRadialGradient(finalX, finalY, 0, finalX, finalY, rad);
        const [r, g, b] = c.rgb;
        
        // Increase alpha slightly for light mode to look rich and painterly
        const currentAlpha = (theme === "dark" ? c.alphaMax : c.alphaMax * 1.5) * (1.0 + clickPulse * 0.4);

        grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${currentAlpha})`);
        grad.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, ${currentAlpha * 0.45})`);
        grad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(finalX, finalY, rad, 0, Math.PI * 2);
        ctx.fill();
      });

      ctx.restore();

      // -----------------------------------------------------------------
      // 2. Draw Floating Organic Matter Particles
      // -----------------------------------------------------------------
      particles.forEach((p) => {
        p.phase += p.phaseSpeed;

        // Organic Brownian-like drift movement
        const driftX = Math.sin(time + p.phase) * 0.16;
        const driftY = Math.cos(time * 0.8 + p.phase) * 0.16;

        p.x += p.vx + driftX;
        p.y += p.vy + driftY;

        // Mouse attraction warp
        if (mouse.active) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 130) {
            const pull = (130 - dist) / 130;
            // Swirl slowly towards mouse
            p.x += (dx / dist) * pull * 0.65;
            p.y += (dy / dist) * pull * 0.65;
          }
        }

        // Boundary wrap-around
        const pad = 10;
        if (p.x < -pad) p.x = w + pad;
        if (p.x > w + pad) p.x = -pad;
        if (p.y < -pad) p.y = h + pad;
        if (p.y > h + pad) p.y = -pad;

        // Sparkle fade effect
        const twinkle = 0.6 + Math.sin(time * 4 + p.phase) * 0.4;
        const displayAlpha = p.alpha * twinkle * (1.0 + clickPulse * 0.6);
        const radius = p.baseRadius * (1.0 + clickPulse * 0.5);

        // HSL Green Tint mapping matching position (green to emerald teal)
        const localHue = p.hue + (p.x / w) * 45;

        // Theme-aware lightness stops to ensure readability on light themes
        const isDark = theme === "dark";
        const glowLightness = isDark ? 75 : 46;
        const coreLightness = isDark ? 88 : 36;

        // Draw particle neon glow
        ctx.fillStyle = `hsla(${localHue}, 100%, ${glowLightness}%, ${displayAlpha * 0.22})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius * 3.8, 0, Math.PI * 2);
        ctx.fill();

        // Draw particle solid core
        ctx.fillStyle = `hsla(${localHue}, 100%, ${coreLightness}%, ${displayAlpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (parent) {
        parent.removeEventListener("mousemove", handleMouseMove);
        parent.removeEventListener("mouseleave", handleMouseLeave);
        parent.removeEventListener("click", handleMouseClick);
      }
      cancelAnimationFrame(animationFrameId);
    };
  }, [theme]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 block w-full h-full pointer-events-none z-[2]"
    />
  );
}