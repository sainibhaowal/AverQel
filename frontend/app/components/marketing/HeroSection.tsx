"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Cpu, Download, FileText, Shield } from "lucide-react";
import { useSyncExternalStore } from "react";
import HeroBackdrop from "./HeroBackdrop";
import HeroAmbientParticles from "./HeroAmbientParticles";
import HeroMorphingBackground from "./HeroMorphingBackground";
import MobileNav from "./MobileNav";
import { useLandingSectionMotion } from "./landingMotion";
import AverQelLogo from "../ui/AverQelLogo";
import {
  APP_VERSION,
  DESKTOP_LINUX_DOWNLOAD_URL,
  DESKTOP_WINDOWS_DOWNLOAD_URL,
} from "@/lib/release";
import { QEL_CONNECT_NAME } from "@/lib/brand";
import { landingAnimatedGradientTextClass } from "./landingType";
import styles from "./LandingVisuals.module.css";

type DesktopPlatform = "linux" | "windows" | "other";

function detectDesktopPlatform(): DesktopPlatform {
  if (typeof navigator === "undefined") return "other";

  const userAgent = navigator.userAgent.toLowerCase();
  if (userAgent.includes("android") || userAgent.includes("iphone")) return "other";
  if (userAgent.includes("windows")) return "windows";
  if (userAgent.includes("linux")) return "linux";
  return "other";
}

const subscribeToPlatform = () => () => undefined;
const getServerDesktopPlatform = (): DesktopPlatform => "other";

const navLinks = [
  { label: "Documents Hub", href: "#documents-hub" },
  { label: "Query", href: "#query" },
  { label: QEL_CONNECT_NAME, href: "#qel-connect" },
  { label: "DeepSpace", href: "#deepspace" },
  { label: "Providers", href: "#providers" },
  { label: "MCP", href: "#mcp" },
  { label: "Controls", href: "#workspace-controls" },
  { label: "Docs", href: "/documentation" },
];

export default function HeroSection() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 9,
    scaleRange: [0.997, 1.003],
  });
  const desktopPlatform = useSyncExternalStore(
    subscribeToPlatform,
    detectDesktopPlatform,
    getServerDesktopPlatform,
  );

  const recommendedDownload = {
    linux: { href: DESKTOP_LINUX_DOWNLOAD_URL, label: "Download for Linux (.deb)" },
    windows: { href: DESKTOP_WINDOWS_DOWNLOAD_URL, label: "Download for Windows (.exe)" },
    other: {
      href: "https://github.com/sainibhaowal/AverQel/releases/latest",
      label: "View Linux and Windows builds",
    },
  }[desktopPlatform];

  return (
    <motion.section ref={ref} className={styles.hero}>
      <HeroBackdrop />
      <div aria-hidden="true" className={styles.heroParticleField} data-hero-particle-field>
        <HeroAmbientParticles />
        <div className={styles.heroParticleCanvasArea} data-hero-focus-animation>
          <HeroMorphingBackground className={styles.heroMorphingCanvas} />
        </div>
        <div className={styles.heroParticleLabels}>
          <span>Runtime visualization</span>
          <span>Particle intelligence field</span>
        </div>
      </div>

      <motion.div style={style} className={styles.heroInner}>
        <nav className={styles.heroNav} aria-label="Main navigation">
          <Link href="/" className="group inline-flex items-center gap-3">
            <AverQelLogo size="nav" />
          </Link>

          <div className={styles.heroNavLinks}>
            {navLinks.map((link) => (
              <Link key={link.label} href={link.href} className={styles.heroNavLink}>
                {link.label}
              </Link>
            ))}
            <Link href="/auth/login" className={styles.heroNavLink}>
              Log in
            </Link>
            <Link
              href="/auth/signup"
              className={`${styles.heroAction} ${styles.heroActionPrimary} !min-h-9 !px-4 !py-2 !text-[0.7rem]`}
            >
              Get started <ArrowRight size={14} />
            </Link>
          </div>

          <MobileNav />
        </nav>

        <div className={styles.heroContent}>
          <div className={styles.heroCopy}>
            <div className={styles.heroKicker}>
              <span className={styles.heroKickerIcon} aria-hidden="true">
                <Cpu size={14} />
              </span>
              AI grounded in your sources
            </div>

            <h1 className={styles.heroTitle}>
              <span className={`${styles.heroTitleAccent} ${landingAnimatedGradientTextClass}`}>
                Intelligence.
              </span>{" "}
              All you need.
            </h1>

            <p className={styles.heroLead}>
              From source documents to grounded answers, collaboration, and DeepSpace projects in
              one workspace, with the models and tools you choose.
            </p>

            <div className={styles.heroVersion}>
              <strong>AverQel {APP_VERSION}</strong>
              <span aria-hidden="true">/</span>
              <span>Desktop and web available</span>
            </div>

            <div className={styles.heroActions}>
              <Link
                href="/auth/signup"
                className={`${styles.heroAction} ${styles.heroActionPrimary}`}
              >
                Create your workspace <ArrowRight size={17} />
              </Link>
              <a
                href={recommendedDownload.href}
                {...(desktopPlatform === "other" ? {} : { download: true })}
                className={styles.heroAction}
              >
                <Download size={16} /> {recommendedDownload.label}
              </a>
            </div>

            <div className={styles.heroTextLinks}>
              <a
                href="https://github.com/sainibhaowal/AverQel/releases/latest"
                className={styles.heroTextLink}
              >
                All desktop builds <ArrowRight size={13} />
              </a>
              <Link href="/documentation/privacy-security" className={styles.heroTextLink}>
                <Shield size={14} /> Security overview
              </Link>
              <Link href="/documentation" className={styles.heroTextLink}>
                <FileText size={14} /> Product docs
              </Link>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.section>
  );
}
