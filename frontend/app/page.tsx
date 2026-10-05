"use client";

import { useEffect } from "react";
import Footer from "@/app/components/layout/Footer";
import HeroSection from "@/app/components/marketing/HeroSection";
import CallToAction from "@/app/components/marketing/CallToAction";
import ProductDomains from "@/app/components/marketing/ProductDomains";
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
        <ProductDomains />
        <CallToAction />
        <Footer />
      </div>
    </main>
  );
}
