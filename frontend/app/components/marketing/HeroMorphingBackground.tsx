"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";

type Particle = {
  x: number;
  y: number;
  z: number;
  targetX: number;
  targetY: number;
  targetZ: number;
  color: string;
  sphereTheta: number;
  spherePhi: number;
  isLand: boolean;
  isPhotonRing: boolean;
  baseSize: number;
  randomOffset: number;
  tempDiskR: number;
};

type TextTarget = {
  x: number;
  y: number;
  z: number;
};

const TWO_PI = Math.PI * 2;
const PHASE_DURATIONS = [460, 420, 460, 420, 460, 420, 460, 420, 460, 420, 620, 620, 220];
const PARTICLE_COUNT_DESKTOP = 8200;
const PARTICLE_COUNT_TABLET = 5200;
const PARTICLE_COUNT_MOBILE = 2800;
const COLORS = ["#00ffa3", "#00b8ff", "#ffffff"] as const;

function sampleTextTargets(text: string, fontSize: number, lines?: string[]) {
  const canvas = document.createElement("canvas");
  canvas.width = 2400;
  canvas.height = 600;

  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return [];
  }

  context.fillStyle = "#000000";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.font = `900 ${fontSize}px "Chakra Petch", "Inter", sans-serif`;
  context.fillStyle = "#ffffff";
  context.textAlign = "center";
  context.textBaseline = "middle";

  if (lines && lines.length > 1) {
    const lineHeight = fontSize * 0.92;
    const totalHeight = lineHeight * (lines.length - 1);

    lines.forEach((line, index) => {
      const y = canvas.height / 2 - totalHeight / 2 + index * lineHeight;
      context.fillText(line, canvas.width / 2, y);
    });
  } else {
    context.fillText(text, canvas.width / 2, canvas.height / 2);
  }

  const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const targets: TextTarget[] = [];

  for (let y = 0; y < canvas.height; y += 4) {
    for (let x = 0; x < canvas.width; x += 4) {
      const index = (y * canvas.width + x) * 4;
      if (data[index] > 128) {
        targets.push({
          x: (x - canvas.width / 2) * 1.45,
          y: (y - canvas.height / 2) * 1.45,
          z: (Math.random() - 0.5) * 24,
        });
      }
    }
  }

  for (let index = targets.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [targets[index], targets[swapIndex]] = [targets[swapIndex], targets[index]];
  }

  return targets;
}

function scaleTargets(targets: TextTarget[], scale: number) {
  if (scale === 1) {
    return targets;
  }

  return targets.map((target) => ({
    x: target.x * scale,
    y: target.y * scale,
    z: target.z * scale,
  }));
}

type HeroMorphingBackgroundProps = {
  className?: string;
};

export default function HeroMorphingBackground({ className }: HeroMorphingBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion || process.env.NODE_ENV === "test") {
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    let width = 0;
    let height = 0;
    let animationFrameId = 0;
    let phase = 0;
    let phaseTimer = 0;
    let time = 0;
    let isVisible = !document.hidden;
    let isInViewport = true;

    let textTargetsArrays: TextTarget[][] = [];

    const particles: Particle[] = [];

    const getParticleCount = () => {
      const viewportWidth = window.innerWidth;

      if (viewportWidth < 640) {
        return PARTICLE_COUNT_MOBILE;
      }

      if (viewportWidth < 1024) {
        return PARTICLE_COUNT_TABLET;
      }

      return PARTICLE_COUNT_DESKTOP;
    };

    const getViewportTuning = () => {
      const viewportWidth = window.innerWidth;

      if (viewportWidth < 640) {
        return {
          textScale: 0.38,
          fov: 1220,
          cameraZ: -1320,
          gridSpacing: 34,
          verticalLift: 72,
          sphereRadius: 430,
          ringRadius: 330,
          helixHeight: 1800,
          funnelHeight: 1800,
          multilineText: true,
        };
      }

      if (viewportWidth < 1024) {
        return {
          textScale: 0.72,
          fov: 920,
          cameraZ: -930,
          gridSpacing: 44,
          verticalLift: 120,
          sphereRadius: 560,
          ringRadius: 430,
          helixHeight: 2200,
          funnelHeight: 2200,
          multilineText: false,
        };
      }

      return {
        textScale: 1,
        fov: 800,
        cameraZ: -800,
        gridSpacing: 54,
        verticalLift: 180,
        sphereRadius: 700,
        ringRadius: 560,
        helixHeight: 2800,
        funnelHeight: 2800,
        multilineText: false,
      };
    };

    const resize = () => {
      const parent = canvas.parentElement;
      width = parent?.clientWidth ?? window.innerWidth;
      height = parent?.clientHeight ?? window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.25);
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const seedParticles = (count: number) => {
      particles.length = 0;

      for (let index = 0; index < count; index += 1) {
        const u = Math.random();
        const v = Math.random();
        const theta = u * TWO_PI;
        const phi = Math.acos(2 * v - 1);
        const nx = Math.sin(phi) * Math.cos(theta);
        const ny = Math.sin(phi) * Math.sin(theta);
        const nz = Math.cos(phi);
        const landMask =
          Math.sin(nx * 5) * Math.cos(ny * 5) + Math.sin(nz * 5) + Math.cos(nx * 2.5);

        particles.push({
          x: (Math.random() - 0.5) * 2800,
          y: (Math.random() - 0.5) * 2800,
          z: (Math.random() - 0.5) * 2800,
          targetX: 0,
          targetY: 0,
          targetZ: 0,
          color: COLORS[index % COLORS.length],
          sphereTheta: theta,
          spherePhi: phi,
          isLand: landMask > 0.3,
          isPhotonRing: index % 10 === 0,
          baseSize: Math.random() * 1.2 + 0.65,
          randomOffset: Math.random() * TWO_PI,
          tempDiskR: 0,
        });
      }
    };

    const rebuildTargets = () => {
      const tuning = getViewportTuning();
      const textConfigs = tuning.multilineText
        ? [
            { text: "AverQel", fontSize: 250 },
            { text: "Axiom Intelligence", fontSize: 176, lines: ["Axiom", "Intelligence"] },
            { text: "Engine Level QX-7", fontSize: 176, lines: ["Engine", "Level", "QX-7"] },
            { text: "DeepSpace Runtime", fontSize: 176, lines: ["DeepSpace", "Runtime"] },
            { text: "Intelligence", fontSize: 216 },
          ]
        : [
            { text: "AverQel", fontSize: 250 },
            { text: "Axiom Intelligence", fontSize: 176 },
            { text: "Engine Level QX-7", fontSize: 176 },
            { text: "DeepSpace Runtime", fontSize: 176 },
            { text: "Intelligence", fontSize: 216 },
          ];

      textTargetsArrays = textConfigs.map((config) =>
        scaleTargets(
          sampleTextTargets(config.text, config.fontSize, config.lines),
          tuning.textScale,
        ),
      );
    };

    const handleResize = () => {
      resize();
      rebuildTargets();
      seedParticles(getParticleCount());
    };

    resize();
    rebuildTargets();
    seedParticles(getParticleCount());

    const render = () => {
      if (!isVisible || !isInViewport) {
        animationFrameId = 0;
        return;
      }

      context.globalCompositeOperation = "source-over";
      context.fillStyle = "rgba(3, 5, 8, 0.22)";
      context.fillRect(0, 0, width, height);
      context.globalCompositeOperation = "lighter";

      time += 0.006;
      phaseTimer += 1;

      if (phaseTimer > PHASE_DURATIONS[phase]) {
        phase = (phase + 1) % PHASE_DURATIONS.length;
        phaseTimer = 0;
      }

      const tuning = getViewportTuning();
      const fov = tuning.fov;
      const cameraZ = tuning.cameraZ;
      const colorBuckets: Record<string, Array<{ x: number; y: number; r: number }>> = {
        "#00ffa3": [],
        "#00b8ff": [],
        "#ffffff": [],
        "#0066ff": [],
      };

      const particleCount = particles.length;

      for (let index = 0; index < particleCount; index += 1) {
        const particle = particles[index];
        const iNorm = index / particleCount;
        const isAmbient = index > particleCount * 0.65;

        if (phase === 0 || phase === 12 || (isAmbient && phase % 2 === 1 && phase < 10)) {
          const gridWidth = 100;
          const mappedIndex = isAmbient ? index * 2 : index;
          const spacing = tuning.gridSpacing;
          const gridX = (mappedIndex % gridWidth) * spacing - (gridWidth * spacing) / 2;
          const gridZ =
            Math.floor(mappedIndex / gridWidth) * spacing -
            ((particleCount / gridWidth) * spacing) / 2;
          const waveY =
            Math.sin(gridX * 0.002 + time) * 360 + Math.cos(gridZ * 0.003 + time * 1.5) * 260;
          const chaos = phase === 12 ? (PHASE_DURATIONS[12] - phaseTimer) * 4 : 0;

          particle.targetX = gridX + Math.sin(time + particle.randomOffset) * chaos;
          particle.targetY =
            waveY + tuning.verticalLift + Math.cos(time + particle.randomOffset) * chaos;
          particle.targetZ = gridZ + ((time * 180) % 260);

          if (isAmbient && phase !== 0 && phase !== 12) {
            particle.targetZ += 600;
          }
        } else if (phase === 2) {
          const phi = Math.acos(-1 + (2 * index) / particleCount);
          const theta = Math.sqrt(particleCount * Math.PI) * phi;
          const pulse =
            390 + Math.sin(time * 4 + particle.randomOffset) * 90 + Math.cos(time * 6) * 45;

          particle.targetX = pulse * Math.cos(theta) * Math.sin(phi);
          particle.targetY = pulse * Math.sin(theta) * Math.sin(phi);
          particle.targetZ = pulse * Math.cos(phi);
        } else if (phase === 4) {
          const clusterIndex = Math.floor(iNorm * 3);
          const clusterT = (iNorm * 3) % 1;
          const clusterCenters = [-0.72, 0, 0.72];
          const clusterSpread = tuning.ringRadius * 0.82;
          const centerX = clusterCenters[clusterIndex] * clusterSpread;
          const arc = Math.sin(clusterT * TWO_PI + time * 0.9);
          const twist = Math.cos(clusterT * TWO_PI * 2 + time * 0.65);
          const flare = 90 + clusterIndex * 32;

          particle.targetX = centerX + arc * flare * 0.7;
          particle.targetY = (clusterIndex - 1) * 155 + twist * 88;
          particle.targetZ =
            Math.sin(clusterT * TWO_PI * 3 + time * 1.15) * (165 + clusterIndex * 26);
        } else if (phase === 6) {
          const strand = index % 2;
          const angle = iNorm * Math.PI * 60 + time * 3;
          const radius = 280 + Math.sin(iNorm * 25 - time * 2) * 74;

          particle.targetX = Math.cos(angle + strand * Math.PI) * radius;
          particle.targetY = iNorm * tuning.helixHeight - tuning.helixHeight / 2;
          particle.targetZ = Math.sin(angle + strand * Math.PI) * radius;
        } else if (phase === 8) {
          const angle = iNorm * TWO_PI * 40;
          const horizontalX = (iNorm - 0.5) * tuning.funnelHeight;
          const radius = 220 + Math.pow(horizontalX / 1200, 2) * 280;

          particle.targetX = horizontalX;
          particle.targetY = Math.cos(angle + time * 2) * radius * 0.42;
          particle.targetZ = Math.sin(angle + time * 2) * radius;
        } else if (phase === 10) {
          const radius = tuning.sphereRadius;
          const currentTheta = particle.sphereTheta + time * 0.4;

          particle.targetX = radius * Math.sin(particle.spherePhi) * Math.cos(currentTheta);
          particle.targetY = radius * Math.cos(particle.spherePhi);
          particle.targetZ = radius * Math.sin(particle.spherePhi) * Math.sin(currentTheta);
        } else if (phase === 11) {
          if (phaseTimer < 150) {
            const collapseScale = Math.max(0, 1 - phaseTimer / 150);
            const radius = tuning.sphereRadius * Math.pow(collapseScale, 3);
            const currentTheta = particle.sphereTheta + time * 0.8;

            particle.targetX = radius * Math.sin(particle.spherePhi) * Math.cos(currentTheta);
            particle.targetY = radius * Math.cos(particle.spherePhi);
            particle.targetZ = radius * Math.sin(particle.spherePhi) * Math.sin(currentTheta);
          } else if (particle.isPhotonRing) {
            const photonRadius = 180 + Math.random() * 8;

            particle.targetX =
              photonRadius *
              Math.sin(particle.spherePhi) *
              Math.cos(particle.sphereTheta + time * 5);
            particle.targetY = photonRadius * Math.cos(particle.spherePhi);
            particle.targetZ =
              photonRadius *
              Math.sin(particle.spherePhi) *
              Math.sin(particle.sphereTheta + time * 5);
          } else {
            const normalizedRadius = Math.pow(iNorm, 1.5);
            const diskRadius = 210 + normalizedRadius * 1200;
            const spiralWarp = diskRadius * 0.006;
            const velocity = time * (2500 / diskRadius);
            const angle = particle.sphereTheta + spiralWarp + velocity;
            const flare = diskRadius / 210;
            const thickness = (Math.random() - 0.5) * 12 * flare;
            const x = diskRadius * Math.cos(angle);
            const z = diskRadius * Math.sin(angle);
            const tilt = 1.25;

            particle.targetX = x;
            particle.targetY = thickness * Math.cos(tilt) - z * Math.sin(tilt);
            particle.targetZ = thickness * Math.sin(tilt) + z * Math.cos(tilt);
            particle.tempDiskR = diskRadius;
          }
        } else if (phase % 2 === 1 && phase < 10 && !isAmbient) {
          const textIndex = Math.floor(phase / 2);
          const targetArray = textTargetsArrays[textIndex];
          const target = targetArray[index % Math.max(1, targetArray.length)];

          if (target) {
            const hoverX = Math.sin(time * 2 + particle.randomOffset) * 6;
            const hoverY = Math.cos(time * 2 + particle.randomOffset) * 6;
            particle.targetX = target.x + hoverX;
            particle.targetY = target.y + hoverY;
            particle.targetZ = target.z;
          }
        }

        const isText = phase % 2 === 1 && phase < 10;
        const baseEase = isText && !isAmbient ? 0.05 : 0.025;
        let activeEase = baseEase;
        let scatterX = 0;
        let scatterY = 0;
        let scatterZ = 0;

        if (phaseTimer < 120 && phase !== 11) {
          const transitionFront = phaseTimer / 120;
          const diff = transitionFront - iNorm;

          if (diff > 0 && diff < 0.4) {
            const intensity = Math.sin((diff / 0.4) * Math.PI);
            const angle = particle.randomOffset + time * 10;

            scatterX = Math.cos(angle) * 400 * intensity;
            scatterY = Math.sin(angle) * 400 * intensity;
            scatterZ = Math.sin(angle * 0.5) * 200 * intensity;
            activeEase = baseEase * 0.5;
          } else if (diff <= 0) {
            activeEase = baseEase * 0.1;
          }
        }

        if (phase === 11 && phaseTimer < 150) {
          activeEase = 0.02 + (phaseTimer / 150) * 0.1;
        } else if (phase === 11 && phaseTimer < 210) {
          activeEase = 0.1;
        }

        particle.x += (particle.targetX + scatterX - particle.x) * activeEase;
        particle.y += (particle.targetY + scatterY - particle.y) * activeEase;
        particle.z += (particle.targetZ + scatterZ - particle.z) * activeEase;

        const scale = fov / (fov + (particle.z - cameraZ));

        if (scale > 0 && scale < 4) {
          const x2d = particle.x * scale + width / 2;
          const y2d = particle.y * scale + height / 2;
          const size2d = particle.baseSize * scale;

          let particleColor = particle.color;

          if (phase === 10 || (phase === 11 && phaseTimer < 150)) {
            particleColor = particle.isLand ? "#00ffa3" : "#0066ff";
            if (Math.abs(Math.cos(particle.spherePhi)) > 0.88) {
              particleColor = "#ffffff";
            }
          } else if (phase === 11 && phaseTimer >= 150) {
            if (particle.isPhotonRing) {
              particleColor = "#ffffff";
            } else if (particle.tempDiskR < 300) {
              particleColor = "#ffffff";
            } else if (particle.tempDiskR < 600) {
              particleColor = "#00ffa3";
            } else {
              particleColor = "#00b8ff";
            }
          }

          if (colorBuckets[particleColor]) {
            colorBuckets[particleColor].push({ x: x2d, y: y2d, r: size2d });
          }
        }
      }

      for (const [color, bucket] of Object.entries(colorBuckets)) {
        if (!bucket.length) {
          continue;
        }

        context.fillStyle = color;
        context.beginPath();

        for (const dot of bucket) {
          context.moveTo(dot.x + dot.r, dot.y);
          context.arc(dot.x, dot.y, dot.r, 0, TWO_PI);
        }

        context.fill();
      }

      animationFrameId = window.requestAnimationFrame(render);
    };

    const ensureRenderLoop = () => {
      if (!animationFrameId && isVisible && isInViewport) {
        animationFrameId = window.requestAnimationFrame(render);
      }
    };

    const handleVisibilityChange = () => {
      isVisible = !document.hidden;
      if (!isVisible && animationFrameId) {
        window.cancelAnimationFrame(animationFrameId);
        animationFrameId = 0;
        return;
      }
      ensureRenderLoop();
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        isInViewport = entry?.isIntersecting ?? true;
        if (!isInViewport && animationFrameId) {
          window.cancelAnimationFrame(animationFrameId);
          animationFrameId = 0;
          return;
        }
        ensureRenderLoop();
      },
      {
        threshold: 0.08,
      },
    );

    window.addEventListener("resize", handleResize);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    observer.observe(canvas);
    ensureRenderLoop();

    return () => {
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      observer.disconnect();
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [reduceMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 z-0 h-full w-full ${className ?? ""}`}
      style={{ background: "#030508" }}
    />
  );
}
