const AVATAR_ART = [
  {
    id: "orbit",
    label: "Orbit",
    colors: ["#0f766e", "#0e7490"],
    art: '<circle cx="48" cy="48" r="19" fill="none" stroke="#e6fffb" stroke-width="5"/><ellipse cx="48" cy="48" rx="36" ry="13" fill="none" stroke="#a7f3d0" stroke-width="4" transform="rotate(-28 48 48)"/><circle cx="75" cy="29" r="5" fill="#fef3c7"/>',
  },
  {
    id: "spark",
    label: "Spark",
    colors: ["#4338ca", "#7c3aed"],
    art: '<path d="M48 17 55 40 78 48 55 56 48 79 41 56 18 48 41 40z" fill="#fff7ed"/><path d="m73 18 3 9 9 3-9 3-3 9-3-9-9-3 9-3z" fill="#c4b5fd"/>',
  },
  {
    id: "comet",
    label: "Comet",
    colors: ["#1d4ed8", "#0891b2"],
    art: '<path d="M65 25c-16-10-38 0-42 20 15-8 30-7 43 2 9 6 14 15 14 27 19-8 28-32 14-47-8-8-19-9-29-2Z" fill="#e0f2fe"/><circle cx="59" cy="45" r="9" fill="#38bdf8"/><path d="M17 78c13-15 27-24 42-29" stroke="#a5f3fc" stroke-width="5" stroke-linecap="round"/>',
  },
  {
    id: "leaf",
    label: "Leaf",
    colors: ["#166534", "#0f766e"],
    art: '<path d="M77 20C48 19 24 32 24 57c0 13 9 22 22 22 25 0 38-25 31-59Z" fill="#dcfce7"/><path d="M25 77c13-17 26-29 44-42M45 59 43 42M57 49l14 2" fill="none" stroke="#15803d" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
  },
  {
    id: "moon",
    label: "Moon",
    colors: ["#312e81", "#1e3a8a"],
    art: '<path d="M63 18c-4 7-6 14-6 22 0 21 17 38 38 38 2 0 4 0 6-.4C93 91 80 99 65 99 42 99 23 80 23 57c0-19 13-35 31-39 3-.7 6-.8 9-.5Z" fill="#fef3c7" transform="translate(-12 -9)"/><circle cx="70" cy="34" r="3" fill="#c4b5fd"/><circle cx="75" cy="64" r="2.5" fill="#c4b5fd"/>',
  },
  {
    id: "mountain",
    label: "Summit",
    colors: ["#92400e", "#be123c"],
    art: '<path d="m14 76 23-37 12 18 13-29 27 48H14Z" fill="#ffedd5"/><path d="m37 39 9 14-9-3-7 4 7-15Zm25-11 11 20-11-5-10 5 10-20Z" fill="#fb7185"/><path d="M14 77h75" stroke="#fff7ed" stroke-width="4" stroke-linecap="round"/>',
  },
  {
    id: "wave",
    label: "Wave",
    colors: ["#0369a1", "#0e7490"],
    art: '<path d="M12 58c12-15 23-15 35 0s23 15 35 0 23-15 35 0v22c-12-15-23-15-35 0s-23 15-35 0-23-15-35 0V58Z" fill="#e0f2fe" transform="translate(-6 -6)"/><path d="M24 35c10-8 19-8 29 0s19 8 29 0" fill="none" stroke="#a5f3fc" stroke-width="5" stroke-linecap="round"/>',
  },
  {
    id: "bot",
    label: "Bot",
    colors: ["#334155", "#475569"],
    art: '<rect x="23" y="28" width="50" height="43" rx="15" fill="#e2e8f0"/><path d="M48 18v10" stroke="#e2e8f0" stroke-width="5" stroke-linecap="round"/><circle cx="48" cy="15" r="5" fill="#67e8f9"/><circle cx="38" cy="47" r="5" fill="#0f766e"/><circle cx="58" cy="47" r="5" fill="#0f766e"/><path d="M38 59h20" stroke="#64748b" stroke-width="4" stroke-linecap="round"/>',
  },
  {
    id: "flower",
    label: "Bloom",
    colors: ["#be185d", "#7c3aed"],
    art: '<g fill="#fce7f3"><ellipse cx="48" cy="30" rx="10" ry="17"/><ellipse cx="48" cy="66" rx="10" ry="17"/><ellipse cx="30" cy="48" rx="17" ry="10"/><ellipse cx="66" cy="48" rx="17" ry="10"/><ellipse cx="35" cy="35" rx="10" ry="16" transform="rotate(-45 35 35)"/><ellipse cx="61" cy="61" rx="10" ry="16" transform="rotate(-45 61 61)"/></g><circle cx="48" cy="48" r="9" fill="#fbbf24"/>',
  },
  {
    id: "prism",
    label: "Prism",
    colors: ["#6d28d9", "#2563eb"],
    art: '<path d="m48 16 29 18-8 34-21 16-21-16-8-34 29-18Z" fill="#ede9fe"/><path d="m48 16 1 68 21-16 8-34-30-18Z" fill="#c4b5fd"/><path d="m27 34 42 0M27 34l22 50m20-50L49 84" fill="none" stroke="#7c3aed" stroke-width="3"/>',
  },
  {
    id: "flame",
    label: "Flame",
    colors: ["#c2410c", "#b91c1c"],
    art: '<path d="M53 14c4 19-13 22-5 40 4-8 11-11 15-20 18 19 15 46-1 55-15 9-39-1-39-23 0-16 10-28 19-37-1 13 4 18 7 20 7-12 4-22 4-35Z" fill="#ffedd5"/><path d="M49 52c11 12 11 24 4 31-6 7-17 2-17-7 0-9 9-17 13-24Z" fill="#fb923c"/>',
  },
  {
    id: "flowering-branch",
    label: "Branch",
    colors: ["#047857", "#4d7c0f"],
    art: '<path d="M25 74c18-10 33-24 48-48M41 60c-1-10-7-15-17-17 2 11 7 17 17 17Zm16-17c10 1 16-4 19-14-11 1-17 5-19 14Zm-7 19c0-10-5-16-15-19 1 11 6 17 15 19Z" fill="#d9f99d" stroke="#ecfccb" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
  },
];

function makeAvatarDataUrl(item: (typeof AVATAR_ART)[number]): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${item.colors[0]}"/><stop offset="1" stop-color="${item.colors[1]}"/></linearGradient></defs><circle cx="48" cy="48" r="48" fill="url(#bg)"/><g stroke-linecap="round" stroke-linejoin="round">${item.art}</g></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export const PROFILE_AVATAR_PRESETS = AVATAR_ART.map((item) => ({
  ...item,
  src: makeAvatarDataUrl(item),
}));
