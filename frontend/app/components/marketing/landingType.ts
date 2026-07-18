export const landingEyebrowClass =
  "text-primary/80 mx-auto w-fit text-center text-[11px] font-bold tracking-[0.3em] uppercase";

export const landingSectionTitleClass =
  "mx-auto mt-4 text-center text-3xl font-semibold tracking-[-0.01em] sm:text-5xl lg:text-[3.55rem] lg:leading-[0.98] [font-family:var(--font-landing-display),var(--font-display),var(--font-inter),sans-serif]";

export const landingSectionLeadClass =
  "text-muted-foreground mx-auto mt-5 text-center text-sm leading-7 sm:text-base sm:leading-8 lg:text-lg";

export const landingHeroTitleClass =
  "max-w-[16ch] text-4xl leading-[0.9] font-semibold tracking-[-0.01em] sm:max-w-none sm:text-6xl lg:text-[4.8rem] [font-family:var(--font-landing-display),var(--font-display),var(--font-inter),sans-serif]";

export const landingFeatureTitleClass =
  "text-3xl leading-[0.95] font-semibold tracking-[-0.01em] sm:text-4xl lg:text-[3.4rem] [font-family:var(--font-landing-display),var(--font-display),var(--font-inter),sans-serif]";

export const landingSectionShellClass =
  "landing-trace-frame relative overflow-hidden px-4 py-16 sm:px-8 sm:py-20 lg:px-12 lg:py-28";

export const landingContentClass = "relative mx-auto w-full max-w-[1800px]";

export const landingHeaderWrapClass = "mx-auto mb-12 max-w-3xl text-center sm:mb-16";

export const landingTitleGradientBySection = {
  hero: "bg-gradient-to-r from-[#f3fff9] via-[#59f2bb] to-[#ff9a3d] bg-clip-text text-transparent",
  supportedFormats:
    "bg-gradient-to-r from-[#d7fff2] via-[#31efb1] to-[#ff9d47] bg-clip-text text-transparent",
  howItWorks:
    "bg-gradient-to-r from-[#f9fff1] via-[#8bf46c] to-[#ffd24a] bg-clip-text text-transparent",
  autonomous:
    "bg-gradient-to-r from-[#f3fffc] via-[#3ef0d2] to-[#7df6ff] bg-clip-text text-transparent",
  orchestration:
    "bg-gradient-to-r from-[#efffff] via-[#1fe2ff] to-[#8f7bff] bg-clip-text text-transparent",
  platformSurfaces:
    "bg-gradient-to-r from-[#fff7ef] via-[#ffb649] to-[#50f0a8] bg-clip-text text-transparent",
  features:
    "bg-gradient-to-r from-[#fff8f0] via-[#ff8d57] to-[#ffe16a] bg-clip-text text-transparent",
  trust: "bg-gradient-to-r from-[#f6fff8] via-[#67ef95] to-[#4ed8ff] bg-clip-text text-transparent",
  techStack:
    "bg-gradient-to-r from-[#fffef5] via-[#ffd76b] to-[#ff8b5e] bg-clip-text text-transparent",
  cta: "bg-gradient-to-r from-[#f3fff7] via-[#72f0a2] to-[#ffab52] bg-clip-text text-transparent",
} as const;
