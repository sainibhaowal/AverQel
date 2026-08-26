const FAVICON = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" fill="none">
  <path d="M16 8h40l8 8v46c0 4-3 8-7 10l-17 6-17-6c-4-2-7-6-7-10V8Z" fill="#07111d" stroke="#06b6d4" stroke-width="3" stroke-linejoin="round"/>
  <path d="M56 8v8h8" stroke="#06b6d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M30 28v26h12c9 0 12-6 12-13s-3-13-12-13H30Z" stroke="#3b82f6" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="50" cy="48" r="5" stroke="#06b6d4" stroke-width="2"/>
  <path d="m54 52 4 4" stroke="#06b6d4" stroke-width="3" stroke-linecap="round"/>
</svg>`;

export const dynamic = "force-static";

export function GET() {
  return new Response(FAVICON.trim(), {
    headers: {
      "Cache-Control": "public, max-age=3600, must-revalidate",
      "Content-Type": "image/svg+xml; charset=utf-8",
    },
  });
}
