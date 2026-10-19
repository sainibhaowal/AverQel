export type ParticlePoint = { x: number; y: number; z: number };

type ArchitectureSegment = { start: ParticlePoint; end: ParticlePoint };

type CycleStage = {
  id: string;
  duration: number;
  textTargetIndex?: number;
  entryMotion?: "scatter" | "flow";
};

export const HERO_CYCLE_STAGES: readonly CycleStage[] = [
  { id: "wave-grid", duration: 460 },
  { id: "averqel", duration: 420, textTargetIndex: 0 },
  { id: "pulsing-sphere", duration: 460 },
  { id: "axiom-intelligence", duration: 420, textTargetIndex: 1 },
  { id: "quantum-architecture", duration: 460, entryMotion: "flow" },
  { id: "engine-level-qx-7", duration: 420, textTargetIndex: 2 },
  { id: "double-helix", duration: 460 },
  { id: "deepspace-runtime", duration: 420, textTargetIndex: 3 },
  { id: "hexagonal-star-tunnel", duration: 460, entryMotion: "flow" },
  { id: "intelligence-into-the-unknown", duration: 420, textTargetIndex: 4 },
  { id: "quantum-entanglement", duration: 560, entryMotion: "flow" },
  { id: "qel-connect", duration: 420, textTargetIndex: 5 },
  { id: "rotating-earth", duration: 620 },
  { id: "collapse-disk", duration: 620 },
  { id: "scatter-reset", duration: 220 },
];

export type TextLineConfig = string | { text: string; fontSize: number };

type HeroTextTargetConfig = {
  text: string;
  fontSize: number;
  mobileLines?: readonly string[];
  lines?: readonly TextLineConfig[];
};

export const HERO_TEXT_TARGETS: readonly HeroTextTargetConfig[] = [
  { text: "AverQel", fontSize: 250 },
  { text: "Axiom Intelligence", fontSize: 176, mobileLines: ["Axiom", "Intelligence"] },
  { text: "Engine Level QX-7", fontSize: 176, mobileLines: ["Engine", "Level", "QX-7"] },
  { text: "DeepSpace Runtime", fontSize: 176, mobileLines: ["DeepSpace", "Runtime"] },
  {
    text: "Intelligence Into the Unknown",
    fontSize: 216,
    lines: [
      { text: "Intelligence", fontSize: 216 },
      { text: "Into the Unknown", fontSize: 112 },
    ],
  },
  {
    text: "Qel Connect Wherever you need",
    fontSize: 190,
    lines: [
      { text: "Qel Connect", fontSize: 190 },
      { text: "Wherever you need", fontSize: 104 },
    ],
  },
];

function hashUnit(value: number) {
  const result = Math.sin(value * 127.1 + 311.7) * 43758.5453;
  return result - Math.floor(result);
}

function buildQuantumArchitectureSegments(): ArchitectureSegment[] {
  const segments: ArchitectureSegment[] = [];
  const addSegment = (start: ParticlePoint, end: ParticlePoint) => segments.push({ start, end });
  const createHexRing = (ringRadius: number, y: number, phase = 0) =>
    Array.from({ length: 6 }, (_, index) => {
      const angle = (index / 6) * Math.PI * 2 + phase;

      return {
        x: Math.cos(angle) * ringRadius,
        y,
        z: Math.sin(angle) * ringRadius,
      };
    });
  const connectLoop = (ring: ParticlePoint[]) => {
    ring.forEach((point, index) => addSegment(point, ring[(index + 1) % ring.length]));
  };
  const decks = [
    { y: -0.43, outer: 0.58, inner: 0.24, phase: 0 },
    { y: 0, outer: 0.42, inner: 0.17, phase: Math.PI / 6 },
    { y: 0.43, outer: 0.58, inner: 0.24, phase: 0 },
  ].map((deck) => ({
    outer: createHexRing(deck.outer, deck.y, deck.phase),
    inner: createHexRing(deck.inner, deck.y, deck.phase + Math.PI / 6),
    core: createHexRing(0.075, deck.y, deck.phase),
  }));

  for (const deck of decks) {
    connectLoop(deck.outer);
    connectLoop(deck.inner);
    connectLoop(deck.core);

    for (let index = 0; index < 6; index += 1) {
      addSegment(deck.outer[index], deck.inner[index]);
      addSegment(deck.inner[index], deck.core[index]);
    }
  }

  for (let deckIndex = 0; deckIndex < decks.length - 1; deckIndex += 1) {
    const lower = decks[deckIndex];
    const upper = decks[deckIndex + 1];

    for (let index = 0; index < 6; index += 1) {
      const nextIndex = (index + 1) % 6;

      addSegment(lower.outer[index], upper.outer[index]);
      addSegment(lower.outer[index], upper.outer[nextIndex]);
      addSegment(lower.inner[index], upper.inner[index]);
      addSegment(lower.inner[index], upper.inner[nextIndex]);
      addSegment(lower.core[index], upper.core[index]);
    }
  }

  const foundation = createHexRing(0.34, -0.68, Math.PI / 6);
  const crown = createHexRing(0.16, 0.7, Math.PI / 6);
  connectLoop(foundation);
  connectLoop(crown);

  for (let index = 0; index < 6; index += 1) {
    addSegment(foundation[index], decks[0].outer[index]);
    addSegment(decks[2].outer[index], crown[index]);
  }

  return segments;
}

const QUANTUM_ARCHITECTURE_SEGMENTS = buildQuantumArchitectureSegments();
export const QUANTUM_ARCHITECTURE_SEGMENT_COUNT = QUANTUM_ARCHITECTURE_SEGMENTS.length;

export function createQuantumArchitectureTarget(
  index: number,
  normalized: number,
  randomOffset: number,
  time: number,
  radius: number,
): ParticlePoint {
  const progress = Math.max(0, Math.min(1, normalized));
  const segmentPosition = progress * QUANTUM_ARCHITECTURE_SEGMENTS.length;
  const segmentIndex = Math.min(
    QUANTUM_ARCHITECTURE_SEGMENTS.length - 1,
    Math.floor(segmentPosition),
  );
  const segment = QUANTUM_ARCHITECTURE_SEGMENTS[segmentIndex];
  const segmentProgress = Math.min(1, segmentPosition - segmentIndex);
  const pulse = 1 + Math.sin(time * 0.7 + segmentIndex * 0.09) * 0.006;
  const rotation = time * 0.055;
  const baseX =
    (segment.start.x + (segment.end.x - segment.start.x) * segmentProgress) * radius * pulse;
  const baseY =
    (segment.start.y + (segment.end.y - segment.start.y) * segmentProgress) * radius * pulse;
  const baseZ =
    (segment.start.z + (segment.end.z - segment.start.z) * segmentProgress) * radius * pulse;
  const rotatedX = baseX * Math.cos(rotation) - baseZ * Math.sin(rotation);
  const rotatedZ = baseX * Math.sin(rotation) + baseZ * Math.cos(rotation);
  const particleDrift = Math.sin(time * 1.2 + randomOffset) * radius * 0.003;
  const structuralGrain = radius * 0.01;

  return {
    x: rotatedX + (hashUnit(index + 11) * 2 - 1) * structuralGrain + particleDrift,
    y: baseY + (hashUnit(index + 23) * 2 - 1) * structuralGrain + particleDrift * 0.4,
    z: rotatedZ + (hashUnit(index + 37) * 2 - 1) * structuralGrain - particleDrift,
  };
}

export function createHexagonalStarTunnelTarget(
  normalized: number,
  sphereTheta: number,
  randomOffset: number,
  time: number,
  tunnelLength: number,
  maxRadius: number,
): ParticlePoint {
  const progress = Math.max(0, Math.min(1, normalized));

  const ringShare = 0.7;
  const ringCount = 7;

  if (progress < ringShare) {
    const ringPosition = (progress / ringShare) * ringCount;
    const ringIndex = Math.min(ringCount - 1, Math.floor(ringPosition));
    const ringDepth = ringIndex / (ringCount - 1);
    const angle = sphereTheta + ringDepth * (Math.PI / 3) + time * 0.08;
    const faceOffset = ((angle + Math.PI / 6) % (Math.PI / 3)) - Math.PI / 6;
    const throat = Math.exp(-Math.pow((ringDepth - 0.5) / 0.22, 2));
    const aperture = maxRadius * (0.9 - throat * 0.27 + Math.cos(ringDepth * Math.PI * 4) * 0.035);
    const hexRadius = aperture / Math.cos(faceOffset);
    const starFacet = 0.87 + Math.cos(angle * 6 + time * 0.28 + ringIndex * 0.18) * 0.13;
    const jitter = 0.94 + hashUnit(randomOffset + ringIndex * 41) * 0.12;
    const radius = hexRadius * starFacet * jitter;
    const centerX = Math.sin(ringDepth * Math.PI * 2 + time * 0.18) * maxRadius * 0.035;
    const centerY = Math.cos(ringDepth * Math.PI * 2 + time * 0.18) * maxRadius * 0.025;

    return {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
      z: (ringDepth - 0.5) * tunnelLength,
    };
  }

  const streamProgress = (progress - ringShare) / (1 - ringShare);
  const streamPosition = streamProgress * 3;
  const streamIndex = Math.min(2, Math.floor(streamPosition));
  const streamT = streamPosition - streamIndex;
  const depth = (streamT - 0.5) * tunnelLength;
  const phase = streamT * Math.PI * 5 + (streamIndex * Math.PI * 2) / 3 + time * 0.48;
  const faceOffset = ((phase + Math.PI / 6) % (Math.PI / 3)) - Math.PI / 6;
  const throat = Math.exp(-Math.pow((streamT - 0.5) / 0.22, 2));
  const aperture = maxRadius * (0.9 - throat * 0.27 + Math.cos(streamT * Math.PI * 4) * 0.035);
  const wallRadius = aperture / Math.cos(faceOffset);
  const orbitRadius = wallRadius * (0.55 + Math.sin(streamT * Math.PI * 2 + streamIndex) * 0.055);
  const particleDrift = (hashUnit(randomOffset + streamIndex * 67) - 0.5) * maxRadius * 0.08;
  const centerX = Math.sin(streamT * Math.PI * 2 + time * 0.18) * maxRadius * 0.035;
  const centerY = Math.cos(streamT * Math.PI * 2 + time * 0.18) * maxRadius * 0.025;

  return {
    x: centerX + Math.cos(phase) * orbitRadius + Math.cos(randomOffset + time) * particleDrift,
    y: centerY + Math.sin(phase) * orbitRadius + Math.sin(randomOffset + time) * particleDrift,
    z: depth + Math.sin(phase * 0.6 + streamIndex) * tunnelLength * 0.012,
  };
}

export function createQuantumEntanglementTarget(
  index: number,
  normalized: number,
  sphereTheta: number,
  spherePhi: number,
  randomOffset: number,
  time: number,
  radius: number,
): ParticlePoint {
  const coreShare = 0.18;

  if (normalized < coreShare) {
    const coreProgress = normalized / coreShare;
    const coreRadius =
      radius * 0.17 * Math.cbrt(coreProgress) * (0.92 + hashUnit(index + 97) * 0.08);
    const pulse = 1 + Math.sin(time * 1.7 + randomOffset) * 0.04;

    return {
      x: Math.sin(spherePhi) * Math.cos(sphereTheta + time * 0.08) * coreRadius * pulse,
      y: Math.cos(spherePhi) * coreRadius * pulse,
      z: Math.sin(spherePhi) * Math.sin(sphereTheta + time * 0.08) * coreRadius * pulse,
    };
  }

  const orbitalProgress = (normalized - coreShare) / (1 - coreShare);
  const orbitIndex = Math.min(2, Math.floor(orbitalProgress * 3));
  const orbitProgress = orbitalProgress * 3 - orbitIndex;
  const angle = orbitProgress * Math.PI * 2 + time * (0.18 + orbitIndex * 0.045);
  const majorRadius = radius * 0.67;
  const tubeRadius = radius * (0.018 + hashUnit(index + 173) * 0.024);
  const tubeAngle = randomOffset + time * 0.7;
  const bandRadius = majorRadius + Math.cos(tubeAngle) * tubeRadius;
  const bandDepth = Math.sin(tubeAngle) * tubeRadius;
  let x: number;
  let y: number;
  let z: number;

  if (orbitIndex === 0) {
    x = Math.cos(angle) * bandRadius;
    y = Math.sin(angle) * bandRadius;
    z = bandDepth;
  } else if (orbitIndex === 1) {
    x = bandDepth;
    y = Math.cos(angle) * bandRadius;
    z = Math.sin(angle) * bandRadius;
  } else {
    x = Math.sin(angle) * bandRadius;
    y = bandDepth;
    z = Math.cos(angle) * bandRadius;
  }

  const rotation = time * 0.12;

  return {
    x: x * Math.cos(rotation) - z * Math.sin(rotation),
    y: y + Math.sin(time * 0.9 + randomOffset) * radius * 0.008,
    z: x * Math.sin(rotation) + z * Math.cos(rotation),
  };
}
