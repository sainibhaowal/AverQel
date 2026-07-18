"use client";

import { motion } from "framer-motion";

const capabilities = [
  {
    label: "Multi-Tenant Isolation",
    detail: "Row-level security",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path
          d="M10 2L3 6v4c0 4.4 3 8.5 7 10 4-1.5 7-5.6 7-10V6l-7-4z"
          stroke="currentColor"
          strokeWidth="1.5"
          fill="none"
        />
      </svg>
    ),
  },
  {
    label: "Vector Search",
    detail: "pgvector cosine similarity",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" fill="none" />
        <path d="M10 6v4l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: "Async Pipeline",
    detail: "Celery + Redis",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path
          d="M4 10h3l2-4 2 8 2-4h3"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    ),
  },
  {
    label: "Citation Engine",
    detail: "Source-referenced answers",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <rect
          x="4"
          y="3"
          width="12"
          height="14"
          rx="2"
          stroke="currentColor"
          strokeWidth="1.5"
          fill="none"
        />
        <path d="M7 7h6M7 10h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: "Full Observability",
    detail: "Prometheus metrics",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <rect
          x="3"
          y="10"
          width="3"
          height="7"
          rx="1"
          stroke="currentColor"
          strokeWidth="1.2"
          fill="none"
        />
        <rect
          x="8.5"
          y="6"
          width="3"
          height="11"
          rx="1"
          stroke="currentColor"
          strokeWidth="1.2"
          fill="none"
        />
        <rect
          x="14"
          y="3"
          width="3"
          height="14"
          rx="1"
          stroke="currentColor"
          strokeWidth="1.2"
          fill="none"
        />
      </svg>
    ),
  },
];

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

export default function CapabilitiesBar() {
  return (
    <section className="relative border-y border-white/5 py-6">
      <div className="absolute inset-0 bg-gradient-to-r from-blue-500/[0.03] via-transparent to-purple-500/[0.03]" />

      <motion.div
        className="relative mx-auto max-w-6xl px-6"
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true }}
      >
        <div className="flex flex-wrap items-center justify-center gap-6 md:gap-10">
          {capabilities.map((cap) => (
            <motion.div
              key={cap.label}
              className="group flex cursor-default items-center gap-2.5"
              variants={itemVariants}
            >
              <span className="text-accent-cyan transition-colors group-hover:text-white">
                {cap.icon}
              </span>
              <div>
                <span className="text-sm font-medium text-slate-300 transition-colors group-hover:text-white">
                  {cap.label}
                </span>
                <span className="ml-2 hidden text-xs text-slate-600 md:inline">{cap.detail}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </section>
  );
}
