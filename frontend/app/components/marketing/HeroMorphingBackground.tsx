"use client";

import { useEffect, useRef } from "react";
import { useLandingReducedMotion } from "./landingMotion";
import {
  createHexagonalStarTunnelTarget,
  createQuantumArchitectureTarget,
  createQuantumEntanglementTarget,
  HERO_CYCLE_STAGES,
  HERO_TEXT_TARGETS,
  QUANTUM_ARCHITECTURE_SEGMENT_COUNT,
  type TextLineConfig,
} from "./heroMorphingCycle";

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
const PARTICLE_COUNT_DESKTOP = 11_000;
const PARTICLE_COUNT_TABLET = 7_000;
const PARTICLE_COUNT_MOBILE = 3_500;
const COLORS = ["#00ffa3", "#00b8ff", "#ffffff"] as const;
const ARCHITECTURE_COLORS = ["#00b8ff", "#54f4ff", "#00ffa3"] as const;
const QUANTUM_COLORS = ["#54f4ff", "#3c9dff", "#8a72ff"] as const;
const TUNNEL_GATE_COLORS = ["#00b8ff", "#54f4ff", "#00ffa3"] as const;
const ENTANGLEMENT_TILT_X = 0.38;
const ENTANGLEMENT_TILT_Y = 0.43;
const ENTANGLEMENT_COS_X = Math.cos(ENTANGLEMENT_TILT_X);
const ENTANGLEMENT_SIN_X = Math.sin(ENTANGLEMENT_TILT_X);
const ENTANGLEMENT_COS_Y = Math.cos(ENTANGLEMENT_TILT_Y);
const ENTANGLEMENT_SIN_Y = Math.sin(ENTANGLEMENT_TILT_Y);

function sampleTextTargets(text: string, fontSize: number, lines?: readonly TextLineConfig[]) {
  const canvas = document.createElement("canvas");
  canvas.width = 2400;
  canvas.height = 600;

  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return [];
  }

  context.fillStyle = "#000000";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ffffff";
  context.textAlign = "center";
  context.textBaseline = "middle";

  if (!lines || lines.length === 0) {
    context.font = `900 ${fontSize}px "Chakra Petch", "Inter", sans-serif`;
    context.fillText(text, canvas.width / 2, canvas.height / 2);
  } else {
    const resolvedLines = lines.map((line) =>
      typeof line === "string" ? { text: line, fontSize } : line,
    );
    const lineGap = fontSize * 0.1;
    const lineHeights = resolvedLines.map((line) => line.fontSize * 0.92);
    const totalHeight =
      lineHeights.reduce((sum, lineHeight) => sum + lineHeight, 0) +
      lineGap * (resolvedLines.length - 1);
    let cursorY = canvas.height / 2 - totalHeight / 2;

    resolvedLines.forEach((line, index) => {
      const lineHeight = lineHeights[index];
      context.font = `900 ${line.fontSize}px "Chakra Petch", "Inter", sans-serif`;
      context.fillText(line.text, canvas.width / 2, cursorY + lineHeight / 2, canvas.width - 48);
      cursorY += lineHeight + lineGap;
    });
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
  const reduceMotion = useLandingReducedMotion();

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
    let focusXRatio = 0.5;
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
          tunnelLength: 900,
          tunnelRadius: 210,
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
          tunnelLength: 1500,
          tunnelRadius: 285,
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
        tunnelLength: 2000,
        tunnelRadius: 330,
        multilineText: false,
      };
    };

    const resize = () => {
      const parent = canvas.parentElement;
      width = parent?.clientWidth ?? window.innerWidth;
      height = parent?.clientHeight ?? window.innerHeight;
      const configuredFocusX = Number.parseFloat(
        parent ? window.getComputedStyle(parent).getPropertyValue("--hero-focus-x") : "",
      );
      focusXRatio = Number.isFinite(configuredFocusX) ? configuredFocusX : 0.5;
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
      textTargetsArrays = HERO_TEXT_TARGETS.map((config) =>
        scaleTargets(
          sampleTextTargets(
            config.text,
            config.fontSize,
            config.lines ?? (tuning.multilineText ? config.mobileLines : undefined),
          ),
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

      context.globalCompositeOperation = "destination-out";
      context.fillStyle = "rgba(0, 0, 0, 0.16)";
      context.fillRect(0, 0, width, height);
      context.globalCompositeOperation = "lighter";

      time += 0.006;
      phaseTimer += 1;

      if (phaseTimer > HERO_CYCLE_STAGES[phase].duration) {
        phase = (phase + 1) % HERO_CYCLE_STAGES.length;
        phaseTimer = 0;
      }

      const stage = HERO_CYCLE_STAGES[phase];
      const isTextStage = stage.textTargetIndex !== undefined;
      const tuning = getViewportTuning();
      const fov = tuning.fov;
      const cameraZ = tuning.cameraZ;
      const colorBuckets: Record<
        string,
        Array<{ x: number; y: number; r: number }>
      > = Object.fromEntries([...COLORS, "#0066ff", ...QUANTUM_COLORS].map((color) => [color, []]));

      const particleCount = particles.length;

      for (let index = 0; index < particleCount; index += 1) {
        const particle = particles[index];
        const iNorm = index / particleCount;
        const isAmbient = index > particleCount * 0.65;

        if (
          stage.id === "wave-grid" ||
          stage.id === "scatter-reset" ||
          (isAmbient && isTextStage)
        ) {
          const gridWidth = 100;
          const mappedIndex = isAmbient ? index * 2 : index;
          const spacing = tuning.gridSpacing;
          const gridX = (mappedIndex % gridWidth) * spacing - (gridWidth * spacing) / 2;
          const gridZ =
            Math.floor(mappedIndex / gridWidth) * spacing -
            ((particleCount / gridWidth) * spacing) / 2;
          const waveY =
            Math.sin(gridX * 0.002 + time) * 360 + Math.cos(gridZ * 0.003 + time * 1.5) * 260;
          const chaos = stage.id === "scatter-reset" ? (stage.duration - phaseTimer) * 4 : 0;

          particle.targetX = gridX + Math.sin(time + particle.randomOffset) * chaos;
          particle.targetY =
            waveY + tuning.verticalLift + Math.cos(time + particle.randomOffset) * chaos;
          particle.targetZ = gridZ + ((time * 180) % 260);

          if (isAmbient && stage.id !== "wave-grid" && stage.id !== "scatter-reset") {
            particle.targetZ += 600;
          }
        } else if (stage.id === "pulsing-sphere") {
          const phi = Math.acos(-1 + (2 * index) / particleCount);
          const theta = Math.sqrt(particleCount * Math.PI) * phi;
          const pulse =
            390 + Math.sin(time * 4 + particle.randomOffset) * 90 + Math.cos(time * 6) * 45;

          particle.targetX = pulse * Math.cos(theta) * Math.sin(phi);
          particle.targetY = pulse * Math.sin(theta) * Math.sin(phi);
          particle.targetZ = pulse * Math.cos(phi);
        } else if (stage.id === "quantum-architecture") {
          const target = createQuantumArchitectureTarget(
            index,
            iNorm,
            particle.randomOffset,
            time,
            tuning.ringRadius * 1.1,
          );
          particle.targetX = target.x;
          particle.targetY = target.y;
          particle.targetZ = target.z;
        } else if (stage.id === "double-helix") {
          const strand = index % 2;
          const angle = iNorm * Math.PI * 60 + time * 3;
          const radius = 280 + Math.sin(iNorm * 25 - time * 2) * 74;

          particle.targetX = Math.cos(angle + strand * Math.PI) * radius;
          particle.targetY = iNorm * tuning.helixHeight - tuning.helixHeight / 2;
          particle.targetZ = Math.sin(angle + strand * Math.PI) * radius;
        } else if (stage.id === "hexagonal-star-tunnel") {
          const target = createHexagonalStarTunnelTarget(
            iNorm,
            particle.sphereTheta,
            particle.randomOffset,
            time,
            tuning.tunnelLength,
            tuning.tunnelRadius,
          );
          particle.targetX = target.x;
          particle.targetY = target.y;
          particle.targetZ = target.z;
        } else if (stage.id === "quantum-entanglement") {
          const target = createQuantumEntanglementTarget(
            index,
            iNorm,
            particle.sphereTheta,
            particle.spherePhi,
            particle.randomOffset,
            time,
            tuning.sphereRadius,
          );
          const tiltedX = target.x * ENTANGLEMENT_COS_Y + target.z * ENTANGLEMENT_SIN_Y;
          const rotatedZ = -target.x * ENTANGLEMENT_SIN_Y + target.z * ENTANGLEMENT_COS_Y;

          particle.targetX = tiltedX;
          particle.targetY = target.y * ENTANGLEMENT_COS_X - rotatedZ * ENTANGLEMENT_SIN_X;
          particle.targetZ = target.y * ENTANGLEMENT_SIN_X + rotatedZ * ENTANGLEMENT_COS_X;
        } else if (stage.id === "rotating-earth") {
          const radius = tuning.sphereRadius;
          const currentTheta = particle.sphereTheta + time * 0.4;

          particle.targetX = radius * Math.sin(particle.spherePhi) * Math.cos(currentTheta);
          particle.targetY = radius * Math.cos(particle.spherePhi);
          particle.targetZ = radius * Math.sin(particle.spherePhi) * Math.sin(currentTheta);
        } else if (stage.id === "collapse-disk") {
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
        } else if (stage.textTargetIndex !== undefined && !isAmbient) {
          const targetArray = textTargetsArrays[stage.textTargetIndex];
          const target = targetArray[index % Math.max(1, targetArray.length)];

          if (target) {
            const hoverX = Math.sin(time * 2 + particle.randomOffset) * 6;
            const hoverY = Math.cos(time * 2 + particle.randomOffset) * 6;
            particle.targetX = target.x + hoverX;
            particle.targetY = target.y + hoverY;
            particle.targetZ = target.z;
          }
        }

        const baseEase =
          stage.id === "quantum-entanglement" || stage.id === "quantum-architecture"
            ? 0.045
            : isTextStage && !isAmbient
              ? 0.05
              : 0.025;
        let activeEase = baseEase;
        let scatterX = 0;
        let scatterY = 0;
        let scatterZ = 0;

        if (phaseTimer < 120 && stage.id !== "collapse-disk" && stage.entryMotion !== "flow") {
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

        if (stage.id === "collapse-disk" && phaseTimer < 150) {
          activeEase = 0.02 + (phaseTimer / 150) * 0.1;
        } else if (stage.id === "collapse-disk" && phaseTimer < 210) {
          activeEase = 0.1;
        }

        particle.x += (particle.targetX + scatterX - particle.x) * activeEase;
        particle.y += (particle.targetY + scatterY - particle.y) * activeEase;
        particle.z += (particle.targetZ + scatterZ - particle.z) * activeEase;

        const scale = fov / (fov + (particle.z - cameraZ));

        if (scale > 0 && scale < 4) {
          const x2d = particle.x * scale + width * focusXRatio;
          const y2d = particle.y * scale + height / 2;
          const size2d = particle.baseSize * scale;

          let particleColor = particle.color;

          if (stage.id === "quantum-architecture") {
            const memberIndex = Math.min(
              QUANTUM_ARCHITECTURE_SEGMENT_COUNT - 1,
              Math.floor(iNorm * QUANTUM_ARCHITECTURE_SEGMENT_COUNT),
            );
            particleColor =
              index % 83 === 0
                ? "#ffffff"
                : ARCHITECTURE_COLORS[memberIndex % ARCHITECTURE_COLORS.length];
          } else if (stage.id === "hexagonal-star-tunnel") {
            if (index % 67 === 0) {
              particleColor = "#ffffff";
            } else if (iNorm < 0.7) {
              const gateIndex = Math.floor((iNorm / 0.7) * 7);
              particleColor = TUNNEL_GATE_COLORS[gateIndex % TUNNEL_GATE_COLORS.length];
            } else {
              const streamIndex = Math.min(2, Math.floor(((iNorm - 0.7) / 0.3) * 3));
              particleColor = QUANTUM_COLORS[streamIndex];
            }
          } else if (stage.id === "quantum-entanglement") {
            if (iNorm < 0.18) {
              particleColor = index % 9 === 0 ? "#ffffff" : "#8a72ff";
            } else {
              const orbitIndex = Math.min(2, Math.floor(((iNorm - 0.18) / 0.82) * 3));
              particleColor = index % 37 === 0 ? "#ffffff" : QUANTUM_COLORS[orbitIndex];
            }
          } else if (
            stage.id === "rotating-earth" ||
            (stage.id === "collapse-disk" && phaseTimer < 150)
          ) {
            particleColor = particle.isLand ? "#00ffa3" : "#0066ff";
            if (Math.abs(Math.cos(particle.spherePhi)) > 0.88) {
              particleColor = "#ffffff";
            }
          } else if (stage.id === "collapse-disk" && phaseTimer >= 150) {
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
        if (stage.id === "quantum-architecture") {
          for (const dot of bucket) {
            const pixelSize = Math.max(1, dot.r * 1.8);
            context.fillRect(dot.x - pixelSize / 2, dot.y - pixelSize / 2, pixelSize, pixelSize);
          }
        } else {
          context.beginPath();

          for (const dot of bucket) {
            context.moveTo(dot.x + dot.r, dot.y);
            context.arc(dot.x, dot.y, dot.r, 0, TWO_PI);
          }

          context.fill();
        }
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
      data-hero-morphing-background
      className={`pointer-events-none absolute inset-0 z-0 h-full w-full ${className ?? ""}`}
    />
  );
}
