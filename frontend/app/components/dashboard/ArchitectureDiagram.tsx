"use client";

import { motion } from "framer-motion";

/* ─── Layout constants ─── */
const COL = { left: 60, center: 320, right: 580 };
const ROW = { r0: 0, r1: 85, r2: 170, r3: 255, r4: 340 };
const NW = 190;
const NH = 62;

interface Node {
  id: string;
  label: string;
  tech: string;
  col: number;
  row: number;
  accent: string;
}

const nodes: Node[] = [
  {
    id: "client",
    label: "Client Application",
    tech: "HTTPS / REST",
    col: COL.center,
    row: ROW.r0,
    accent: "#64748b",
  },
  {
    id: "api",
    label: "FastAPI Gateway",
    tech: "Auth / RBAC / Rate Limit",
    col: COL.center,
    row: ROW.r1,
    accent: "#3b82f6",
  },
  {
    id: "auth",
    label: "Auth Module",
    tech: "JWT + Argon2",
    col: COL.left,
    row: ROW.r1,
    accent: "#a855f7",
  },
  {
    id: "worker",
    label: "Celery Workers",
    tech: "Ingestion Pipeline",
    col: COL.left,
    row: ROW.r2,
    accent: "#8b5cf6",
  },
  {
    id: "beat",
    label: "Celery Beat",
    tech: "Scheduled Tasks",
    col: COL.left,
    row: ROW.r3,
    accent: "#6366f1",
  },
  {
    id: "pg",
    label: "PostgreSQL",
    tech: "pgvector + RLS",
    col: COL.center,
    row: ROW.r3,
    accent: "#06b6d4",
  },
  {
    id: "redis",
    label: "Redis",
    tech: "Cache + Message Broker",
    col: COL.center,
    row: ROW.r4,
    accent: "#ef4444",
  },
  {
    id: "minio",
    label: "MinIO",
    tech: "S3 Object Storage",
    col: COL.right,
    row: ROW.r2,
    accent: "#f59e0b",
  },
  {
    id: "prom",
    label: "Prometheus",
    tech: "Metrics Collection",
    col: COL.right,
    row: ROW.r3,
    accent: "#22c55e",
  },
];

interface Edge {
  from: string;
  to: string;
  label: string;
}

const edges: Edge[] = [
  { from: "client", to: "api", label: "HTTPS" },
  { from: "api", to: "auth", label: "Verify" },
  { from: "api", to: "pg", label: "SQL" },
  { from: "api", to: "redis", label: "Cache" },
  { from: "api", to: "worker", label: "Task" },
  { from: "api", to: "minio", label: "Read" },
  { from: "worker", to: "pg", label: "Write" },
  { from: "worker", to: "minio", label: "S3" },
  { from: "worker", to: "redis", label: "Ack" },
  { from: "beat", to: "redis", label: "Cron" },
  { from: "prom", to: "api", label: "Scrape" },
];

function cx(n: Node) {
  return n.col + NW / 2;
}
function cy(n: Node) {
  return n.row + NH / 2;
}

function edgePath(a: Node, b: Node) {
  const x1 = cx(a),
    y1 = cy(a),
    x2 = cx(b),
    y2 = cy(b);
  const mx = (x1 + x2) / 2,
    my = (y1 + y2) / 2;
  // Slight curve
  const dx = x2 - x1,
    dy = y2 - y1;
  const cx1 = mx - dy * 0.08,
    cy1 = my + dx * 0.08;
  return {
    path: `M${x1},${y1} Q${cx1},${cy1} ${x2},${y2}`,
    mx: (x1 + cx1 + x2) / 3,
    my: (y1 + cy1 + y2) / 3,
  };
}

export default function ArchitectureDiagram() {
  return (
    <section id="architecture" className="relative px-4 py-20 sm:px-6 sm:py-28">
      {/* Subtle background grid */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `radial-gradient(circle, rgba(148,163,184,0.8) 1px, transparent 1px)`,
          backgroundSize: "32px 32px",
        }}
      />

      <div className="relative mx-auto max-w-5xl">
        {/* Header */}
        <motion.div
          className="mb-16 text-center"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <p className="text-accent-cyan mb-3 font-mono text-sm tracking-widest uppercase">
            Infrastructure
          </p>
          <h2 className="text-foreground mb-4 text-3xl font-black md:text-5xl">
            System Architecture
          </h2>
          <p className="text-muted-foreground mx-auto max-w-xl text-base">
            Nine interconnected services running on your own infrastructure
          </p>
        </motion.div>

        {/* Diagram */}
        <motion.div
          className="theme-panel relative overflow-x-auto rounded-2xl border p-6 shadow-[0_0_80px_rgba(var(--primary),0.04),0_20px_60px_rgba(0,0,0,0.1)] transition-all md:p-14"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.15 }}
        >
          {/* Inner dot grid */}
          <div
            className="absolute inset-0 rounded-2xl opacity-[0.04]"
            style={{
              backgroundImage: `radial-gradient(circle, rgba(148,163,184,1) 0.5px, transparent 0.5px)`,
              backgroundSize: "24px 24px",
            }}
          />

          <svg
            viewBox="0 -50 830 510"
            className="relative z-10 w-full min-w-[560px] sm:min-w-[650px]"
            fill="none"
          >
            <defs>
              <linearGradient id="agEdge" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(59,130,246,0.5)" />
                <stop offset="100%" stopColor="rgba(6,182,212,0.3)" />
              </linearGradient>
              <filter id="agGlow">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Edges */}
            {edges.map((e, i) => {
              const a = nodes.find((n) => n.id === e.from)!;
              const b = nodes.find((n) => n.id === e.to)!;
              const { path, mx, my } = edgePath(a, b);
              return (
                <motion.g
                  key={`e-${i}`}
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.5 + i * 0.04, duration: 0.4 }}
                >
                  <path d={path} stroke="rgba(148,163,184,0.1)" strokeWidth="1.5" fill="none" />
                  {/* Animated dot traveling along edge */}
                  <circle r={2} fill="var(--accent-cyan)" opacity={0.6}>
                    <animateMotion dur={`${3 + i * 0.4}s`} repeatCount="indefinite" path={path} />
                  </circle>
                  {/* Label */}
                  <rect
                    x={mx - 18}
                    y={my - 7}
                    width="36"
                    height="14"
                    rx="4"
                    fill="rgba(8,12,22,0.95)"
                    stroke="rgba(148,163,184,0.1)"
                    strokeWidth="0.5"
                  />
                  <text
                    x={mx}
                    y={my + 3.5}
                    textAnchor="middle"
                    fontSize="7"
                    fill="rgba(148,163,184,0.45)"
                    fontFamily="var(--font-jetbrains-mono), monospace"
                    fontWeight="500"
                  >
                    {e.label}
                  </text>
                </motion.g>
              );
            })}

            {/* Nodes */}
            {nodes.map((node, i) => (
              <motion.g
                key={node.id}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.2 + i * 0.06, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              >
                {/* Shadow/glow under node */}
                <rect
                  x={node.col + 4}
                  y={node.row + 4}
                  width={NW}
                  height={NH}
                  rx="12"
                  fill={node.accent}
                  opacity="0.05"
                  filter="url(#agGlow)"
                />
                {/* Main box */}
                <rect
                  x={node.col}
                  y={node.row}
                  width={NW}
                  height={NH}
                  rx="12"
                  fill="var(--surface-0)"
                  stroke={node.accent}
                  strokeWidth="1"
                  strokeOpacity="0.4"
                />
                {/* Left accent bar */}
                <rect
                  x={node.col}
                  y={node.row + 12}
                  width="3"
                  height={NH - 24}
                  rx="1.5"
                  fill={node.accent}
                  opacity="0.8"
                />
                {/* Status dot */}
                <circle
                  cx={node.col + NW - 16}
                  cy={node.row + 14}
                  r={3}
                  fill={node.accent}
                  opacity={0.6}
                >
                  <animate
                    attributeName="opacity"
                    values="0.3;0.8;0.3"
                    dur="3s"
                    repeatCount="indefinite"
                  />
                </circle>
                {/* Label */}
                <text
                  x={node.col + 16}
                  y={node.row + 26}
                  fontSize="11"
                  fontWeight="800"
                  fill="var(--foreground)"
                  fontFamily="var(--font-inter), sans-serif"
                >
                  {node.label}
                </text>
                {/* Tech label */}
                <text
                  x={node.col + 16}
                  y={node.row + 44}
                  fontSize="8.5"
                  fill="rgba(148,163,184,0.5)"
                  fontFamily="var(--font-jetbrains-mono), monospace"
                >
                  {node.tech}
                </text>
              </motion.g>
            ))}
          </svg>
        </motion.div>
      </div>
    </section>
  );
}
