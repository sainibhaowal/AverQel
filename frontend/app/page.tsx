"use client";

import { useEffect } from "react";
import Footer from "@/app/components/layout/Footer";
import HeroSection from "@/app/components/marketing/HeroSection";
import SupportedFormats from "@/app/components/marketing/SupportedFormats";
import HowItWorks from "@/app/components/marketing/HowItWorks";
import ProductWalkthrough from "@/app/components/marketing/ProductWalkthrough";
import PlatformSurfaces from "@/app/components/marketing/PlatformSurfaces";
import ProductScreenshotGallery from "@/app/components/marketing/ProductScreenshotGallery";
import FeaturesGrid from "@/app/components/marketing/FeaturesGrid";
import TrustCommitments from "@/app/components/marketing/TrustCommitments";
import TechStackMarquee from "@/app/components/marketing/TechStackMarquee";
import CallToAction from "@/app/components/marketing/CallToAction";
import { LandingScrollEffects } from "@/app/components/marketing/landingMotion";

export default function Home() {
  useEffect(() => {
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
    window.scrollTo(0, 0);
  }, []);

  return (
    <main className="dark landing-cyber bg-background relative isolate min-h-[100svh] overflow-x-hidden transition-colors duration-500">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute inset-0 bg-[#030508]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,163,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,163,0.08)_1px,transparent_1px),linear-gradient(rgba(0,184,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(0,184,255,0.04)_1px,transparent_1px)] bg-[size:32px_32px,32px_32px,128px_128px,128px_128px] opacity-72" />
      </div>
      <LandingScrollEffects />
      <div className="relative z-10">
        <HeroSection />
        <SupportedFormats />
        <HowItWorks />
        <ProductWalkthrough />
        <PlatformSurfaces />
        <ProductScreenshotGallery />
        <FeaturesGrid />
        <TrustCommitments />
        <TechStackMarquee />
        <CallToAction />
        <Footer />
      </div>
    </main>
  );
}
