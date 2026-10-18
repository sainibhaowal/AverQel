"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  CircleGauge,
  Database,
  Search,
  Share2,
  Sparkles,
  Workflow,
} from "lucide-react";
import styles from "./LandingVisuals.module.css";
import { useLandingSectionMotion } from "./landingMotion";

const workspaceAreas = [
  { label: "Documents Hub", detail: "SOURCE FILES", icon: Database },
  { label: "Grounded Query", detail: "SOURCE ANSWERS", icon: Search },
  { label: "Qel Connect", detail: "SHARED SPACE", icon: Share2 },
  { label: "DeepSpace", detail: "AGENT WORK", icon: Workflow },
];

export default function CallToAction() {
  const reduceMotion = useReducedMotion();
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 12,
    scaleRange: [0.998, 1.003],
  });

  return (
    <motion.section ref={ref} className={`landing-trace-frame ${styles.ctaSection}`}>
      <motion.div style={style} className={styles.ctaFrame}>
        <div className={styles.ctaTopbar}>
          <span className={styles.ctaSystemLabel}>
            <CircleGauge size={14} aria-hidden="true" /> AVERQEL / WORKSPACE SYSTEM
          </span>
          <span className={styles.ctaSystemStatus}>
            <span aria-hidden="true" /> YOUR WORKSPACE. YOUR CONTROL.
          </span>
        </div>

        <div className={styles.ctaContent}>
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, x: -18 }}
            whileInView={reduceMotion ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: false, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
            className={styles.ctaCopy}
          >
            <div className={styles.ctaEyebrow}>
              <Sparkles size={14} aria-hidden="true" /> YOUR NEXT WORKSPACE
            </div>
            <h2 className={styles.ctaTitle}>
              Build on what <span>you know.</span>
              <span className={styles.ctaTitleAccent}>Keep what matters.</span>
            </h2>
            <p className={styles.ctaLead}>
              Bring documents, grounded answers, shared projects, and AI work together. Choose the
              tools and services that fit the way you work.
            </p>
            <div className={styles.ctaFootnote}>
              <span>ONE WORKSPACE</span>
              <span aria-hidden="true">/</span>
              <span>YOUR TOOLS</span>
              <span aria-hidden="true">/</span>
              <span>YOUR CONTROLS</span>
            </div>
          </motion.div>

          <motion.div
            aria-hidden="true"
            initial={reduceMotion ? false : { opacity: 0, scale: 0.88 }}
            whileInView={reduceMotion ? undefined : { opacity: 1, scale: 1 }}
            viewport={{ once: false, amount: 0.2 }}
            transition={{ duration: 0.7, ease: "easeOut", delay: 0.08 }}
            className={styles.ctaOrbit}
          >
            <motion.div
              className={`${styles.ctaOrbitRing} ${styles.ctaOrbitRingOuter}`}
              animate={reduceMotion ? undefined : { rotate: 360 }}
              transition={{ duration: 38, repeat: Infinity, ease: "linear" }}
            >
              <span className={styles.ctaOrbitNode} />
            </motion.div>
            <motion.div
              className={`${styles.ctaOrbitRing} ${styles.ctaOrbitRingInner}`}
              animate={reduceMotion ? undefined : { rotate: -360 }}
              transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
            >
              <span className={styles.ctaOrbitNodeAlt} />
            </motion.div>
            <div className={styles.ctaCorePosition}>
              <motion.div
                className={styles.ctaCore}
                animate={
                  reduceMotion
                    ? undefined
                    : {
                        y: [0, -4, 0],
                        boxShadow: [
                          "0 0 32px rgba(0,255,163,0.12)",
                          "0 0 62px rgba(0,184,255,0.24)",
                          "0 0 32px rgba(0,255,163,0.12)",
                        ],
                      }
                }
                transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
              >
                <Bot size={34} strokeWidth={1.65} />
              </motion.div>
            </div>
            <span className={`${styles.ctaOrbitLabel} ${styles.ctaOrbitLabelTop}`}>MODEL</span>
            <span className={`${styles.ctaOrbitLabel} ${styles.ctaOrbitLabelRight}`}>TOOLS</span>
            <span className={`${styles.ctaOrbitLabel} ${styles.ctaOrbitLabelBottom}`}>SOURCES</span>
            <span className={`${styles.ctaOrbitLabel} ${styles.ctaOrbitLabelLeft}`}>WORK</span>
          </motion.div>

          <motion.div
            initial={reduceMotion ? false : { opacity: 0, x: 18 }}
            whileInView={reduceMotion ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: false, amount: 0.2 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.12 }}
            className={styles.ctaConsole}
          >
            <div className={styles.ctaConsoleHeader}>
              <span>
                <CircleGauge size={15} aria-hidden="true" /> WORKSPACE OVERVIEW
              </span>
              <span className={styles.ctaConsoleState}>READY TO EXPLORE</span>
            </div>
            <p className={styles.ctaConsoleIntro}>
              <strong>Start with the area you need.</strong>
              Configure only the services you choose to use.
            </p>
            <div className={styles.ctaAreaGrid}>
              {workspaceAreas.map(({ label, detail, icon: Icon }, index) => (
                <div className={styles.ctaArea} key={label}>
                  <span className={styles.ctaAreaIcon}>
                    <Icon size={16} aria-hidden="true" />
                  </span>
                  <span className={styles.ctaAreaCopy}>
                    <strong>{label}</strong>
                    <small>{detail}</small>
                  </span>
                  <span className={styles.ctaAreaIndex} aria-hidden="true">
                    0{index + 1}
                  </span>
                </div>
              ))}
            </div>
            <div className={styles.ctaActions}>
              <Link href="/auth/signup" className={styles.ctaPrimaryAction}>
                Start using AverQel <ArrowRight size={16} aria-hidden="true" />
              </Link>
              <Link href="/documentation" className={styles.ctaSecondaryAction}>
                Explore the docs
              </Link>
            </div>
            <Link href="/auth/login" className={styles.ctaLoginLink}>
              Already have an account? <span>Log in</span>
            </Link>
          </motion.div>
        </div>

        <div className={styles.ctaBottomline}>
          <span>DOCUMENTS</span>
          <span>GROUNDED QUERY</span>
          <span>QEL CONNECT</span>
          <span>DEEPSPACE</span>
          <span>MODEL &amp; TOOL CONTROLS</span>
        </div>
      </motion.div>
    </motion.section>
  );
}
