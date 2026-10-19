import { describe, expect, it } from "vitest";
import {
  createHexagonalStarTunnelTarget,
  createQuantumArchitectureTarget,
  createQuantumEntanglementTarget,
  HERO_CYCLE_STAGES,
  HERO_TEXT_TARGETS,
  QUANTUM_ARCHITECTURE_SEGMENT_COUNT,
} from "../app/components/marketing/heroMorphingCycle";

describe("landing hero particle cycle", () => {
  it("keeps all requested stages in one ordered loop", () => {
    expect(HERO_CYCLE_STAGES.map(({ id }) => id)).toEqual([
      "wave-grid",
      "averqel",
      "pulsing-sphere",
      "axiom-intelligence",
      "quantum-architecture",
      "engine-level-qx-7",
      "double-helix",
      "deepspace-runtime",
      "hexagonal-star-tunnel",
      "intelligence-into-the-unknown",
      "quantum-entanglement",
      "qel-connect",
      "rotating-earth",
      "collapse-disk",
      "scatter-reset",
    ]);

    expect(HERO_CYCLE_STAGES.at(-1)?.duration).toBeGreaterThan(0);
    expect(HERO_CYCLE_STAGES[9].textTargetIndex).toBe(4);
    expect(HERO_CYCLE_STAGES[4].id).toBe("quantum-architecture");
    expect(HERO_CYCLE_STAGES[4].entryMotion).toBe("flow");
    expect(HERO_CYCLE_STAGES[10].id).toBe("quantum-entanglement");
    expect(HERO_CYCLE_STAGES[10].entryMotion).toBe("flow");
    expect(HERO_CYCLE_STAGES[11].textTargetIndex).toBe(5);
    expect(HERO_CYCLE_STAGES[8].entryMotion).toBe("flow");
  });

  it("puts the two new taglines on separate particle text lines", () => {
    expect(HERO_TEXT_TARGETS[4].lines).toEqual([
      { text: "Intelligence", fontSize: 216 },
      { text: "Into the Unknown", fontSize: 112 },
    ]);
    expect(HERO_TEXT_TARGETS[5].lines).toEqual([
      { text: "Qel Connect", fontSize: 190 },
      { text: "Wherever you need", fontSize: 104 },
    ]);
  });

  it("forms a connected, three-tier particle architecture", () => {
    const sampleCount = QUANTUM_ARCHITECTURE_SEGMENT_COUNT * 8;
    const points = Array.from({ length: sampleCount }, (_, index) => {
      const normalized = (index + 0.5) / sampleCount;
      return createQuantumArchitectureTarget(index, normalized, index * 0.17, 0, 500);
    });
    const spread = (axis: "x" | "y" | "z") =>
      Math.max(...points.map((point) => point[axis])) -
      Math.min(...points.map((point) => point[axis]));
    const maximumRadius = Math.max(...points.map((point) => Math.hypot(point.x, point.y, point.z)));

    expect(QUANTUM_ARCHITECTURE_SEGMENT_COUNT).toBeGreaterThan(160);
    expect(spread("x")).toBeGreaterThan(500);
    expect(spread("y")).toBeGreaterThan(600);
    expect(spread("z")).toBeGreaterThan(500);
    expect(maximumRadius).toBeLessThan(420);
  });

  it("forms a quantum nucleus with three distinct orbital bands", () => {
    const points = Array.from({ length: 1_200 }, (_, index) => {
      const normalized = index / 1_200;
      return {
        normalized,
        point: createQuantumEntanglementTarget(
          index,
          normalized,
          index * 2.399963,
          Math.acos(1 - 2 * ((index * 0.61803398875) % 1)),
          index * 0.17,
          0,
          1_000,
        ),
      };
    });
    const corePoints = points.filter(({ normalized }) => normalized < 0.18);
    const coreRadius = Math.max(
      ...corePoints.map(({ point }) => Math.hypot(point.x, point.y, point.z)),
    );

    expect(coreRadius).toBeLessThan(180);

    for (let orbitIndex = 0; orbitIndex < 3; orbitIndex += 1) {
      const orbitPoints = points.filter(({ normalized }) => {
        if (normalized < 0.18) return false;
        return Math.min(2, Math.floor(((normalized - 0.18) / 0.82) * 3)) === orbitIndex;
      });
      const crossSection = (point: { x: number; y: number; z: number }) =>
        orbitIndex === 0 ? point.z : orbitIndex === 1 ? point.x : point.y;
      const orbitalRadius = (point: { x: number; y: number; z: number }) =>
        orbitIndex === 0
          ? Math.hypot(point.x, point.y)
          : orbitIndex === 1
            ? Math.hypot(point.y, point.z)
            : Math.hypot(point.x, point.z);

      expect(orbitPoints.length).toBeGreaterThan(300);
      expect(
        Math.max(...orbitPoints.map(({ point }) => Math.abs(crossSection(point)))),
      ).toBeLessThan(60);
      expect(Math.min(...orbitPoints.map(({ point }) => orbitalRadius(point)))).toBeGreaterThan(
        600,
      );
      expect(Math.max(...orbitPoints.map(({ point }) => orbitalRadius(point)))).toBeLessThan(740);
    }
  });

  it("forms a star-cut iris portal with a pinched throat and twisted streams", () => {
    const ringPoint = (ringIndex: number) =>
      createHexagonalStarTunnelTarget(((ringIndex + 0.5) / 7) * 0.7, 0.4, 0.8, 1, 2_000, 500);

    const entrance = ringPoint(0);
    const throat = ringPoint(3);
    const exit = ringPoint(6);
    const radius = (point: { x: number; y: number }) => Math.hypot(point.x, point.y);
    const streamStart = createHexagonalStarTunnelTarget(0.71, 0.4, 0.8, 1, 2_000, 500);
    const streamEnd = createHexagonalStarTunnelTarget(0.79, 0.4, 0.8, 1, 2_000, 500);

    expect(entrance.z).toBeLessThan(throat.z);
    expect(exit.z).toBeGreaterThan(throat.z);
    expect(radius(entrance)).toBeGreaterThan(radius(throat) * 1.15);
    expect(radius(exit)).toBeGreaterThan(radius(throat) * 1.15);
    expect(streamEnd.z - streamStart.z).toBeGreaterThan(1_400);
  });
});
