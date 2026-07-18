"use client";

import { motion } from "framer-motion";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingHeaderWrapClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const technologies = [
  { name: "FastAPI", color: "#009688" },
  { name: "Python 3.12", color: "#3776ab" },
  { name: "PostgreSQL", color: "#336791" },
  { name: "pgvector", color: "#06b6d4" },
  { name: "Redis", color: "#dc382d" },
  { name: "Celery", color: "#37814a" },
  { name: "OAuth2 | PAT", color: "#8b5cf6" },
  { name: "BeautifulSoup", color: "#6ca000" },
  { name: "httpx", color: "#009688" },
  { name: "Docker", color: "#2496ed" },
  { name: "Prometheus", color: "#e6522c" },
  { name: "SQLAlchemy", color: "#d71f00" },
  { name: "Pydantic", color: "#e92063" },
  { name: "JWT", color: "#d63aff" },
  { name: "Argon2", color: "#8b5cf6" },
  { name: "Next.js", color: "#ffffff" },
  { name: "React 19", color: "#61dafb" },
  { name: "TypeScript", color: "#3178c6" },
  { name: "Tailwind CSS", color: "#38bdf8" },
];

export default function TechStackMarquee() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 10,
    scaleRange: [0.996, 1.004],
  });

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        {/* Header */}
        <motion.div
          className={`relative ${landingHeaderWrapClass}`}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <p className="text-primary/80 text-[11px] font-bold tracking-[0.3em] uppercase">
            Built With
          </p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.techStack} mt-3`}
          >
            Established, production-tested technologies
          </h2>
          <p className={`${landingSectionLeadClass} mx-auto mt-3 max-w-xl text-slate-500`}>
            No experimental frameworks. Every component in the stack is well-documented,
            battle-tested, and actively maintained.
          </p>
        </motion.div>

        {/* Marquee */}
        <div className="relative">
          {/* Fade edges */}
          <div className="absolute top-0 bottom-0 left-0 z-10 w-16 bg-gradient-to-r from-[#030508] to-transparent sm:w-32" />
          <div className="absolute top-0 right-0 bottom-0 z-10 w-16 bg-gradient-to-l from-[#030508] to-transparent sm:w-32" />

          <div className="animate-marquee flex hover:[animation-play-state:paused]">
            {[...technologies, ...technologies].map((tech, i) => (
              <div key={`${tech.name}-${i}`} className="mx-2.5 flex-shrink-0 sm:mx-3">
                <div className="flex items-center gap-2.5 rounded-full border border-white/[0.06] bg-white/[0.02] px-4 py-2.5 transition hover:border-white/[0.12] hover:bg-white/[0.04] sm:px-5">
                  <span
                    className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: tech.color }}
                  />
                  <span className="text-xs font-medium whitespace-nowrap text-slate-400 transition-colors group-hover:text-white sm:text-sm">
                    {tech.name}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.section>
  );
}
