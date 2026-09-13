"use client";

import { useEffect } from "react";
import Footer from "@/app/components/layout/Footer";
import HeroSection from "@/app/components/marketing/HeroSection";
import SupportedFormats from "@/app/components/marketing/SupportedFormats";
import HowItWorks from "@/app/components/marketing/HowItWorks";
import ProductWalkthrough from "@/app/components/marketing/ProductWalkthrough";
import CollectionCollaboration from "@/app/components/marketing/CollectionCollaboration";
import WorkspaceOrbit from "@/app/components/marketing/WorkspaceOrbit";
import WorkspaceIntelligence from "@/app/components/marketing/WorkspaceIntelligence";
import PlatformSurfaces from "@/app/components/marketing/PlatformSurfaces";
import ProductScreenshotGallery from "@/app/components/marketing/ProductScreenshotGallery";
import FeaturesGrid from "@/app/components/marketing/FeaturesGrid";
import UseCases from "@/app/components/marketing/UseCases";
import ControlCenter from "@/app/components/marketing/ControlCenter";
import TrustCommitments from "@/app/components/marketing/TrustCommitments";
import TechStackMarquee from "@/app/components/marketing/TechStackMarquee";
import CallToAction from "@/app/components/marketing/CallToAction";
import CapabilityDirectory from "@/app/components/marketing/CapabilityDirectory";
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
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(0,255,163,0.2)_1px,transparent_1.35px),radial-gradient(circle_at_1px_1px,rgba(0,184,255,0.1)_1px,transparent_1.35px)] bg-[size:32px_32px,128px_128px] opacity-72" />
      </div>
      <LandingScrollEffects />
      <div className="relative z-10">
        <HeroSection />
        <CapabilityDirectory />
        <details className="group relative z-10 mx-4 mb-8 rounded-3xl border border-white/[0.09] bg-slate-950/35 backdrop-blur-md sm:mx-8 lg:mx-12">
          <summary className="cursor-pointer list-none px-5 py-5 text-sm font-bold text-slate-200 transition-colors marker:hidden hover:text-white sm:px-7">
            <span className="mr-3 inline-flex rounded-full border border-[#00ffa3]/25 bg-[#00ffa3]/10 px-2.5 py-1 text-[10px] font-black tracking-[0.14em] text-[#8effd2] uppercase">
              Optional detail
            </span>
            Explore the full product story
            <span className="ml-2 text-slate-500 transition-transform group-open:inline-block group-open:rotate-180">
              ⌄
            </span>
          </summary>
          <div className="border-t border-white/[0.07]">
            <SupportedFormats />
            <HowItWorks />
            <WorkspaceOrbit />
            <ProductWalkthrough />
            <CollectionCollaboration />
            <PlatformSurfaces />
            <WorkspaceIntelligence />
            <ProductScreenshotGallery />
            <UseCases />
            <FeaturesGrid />
            <ControlCenter />
          </div>
        </details>
        <TrustCommitments />
        <TechStackMarquee />
        <CallToAction />
        <Footer />
      </div>
    </main>
  );
}
