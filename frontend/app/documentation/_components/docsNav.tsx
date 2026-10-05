import { ReactNode } from "react";
import {
  BookOpen,
  Boxes,
  CalendarClock,
  FileStack,
  FolderKanban,
  HeartHandshake,
  HelpCircle,
  Home,
  Layers3,
  Network,
  Search,
  Settings,
  Shield,
  Sparkles,
  Waypoints,
  Zap,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon?: ReactNode;
  items?: NavItem[];
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

/** Public documentation follows the product's actual top-level work areas. */
export const docsNavGroups: NavGroup[] = [
  {
    group: "Start here",
    items: [
      { title: "Documentation home", href: "/documentation", icon: <Home size={14} /> },
      {
        title: "What is AverQel?",
        href: "/documentation/what-is-averqel",
        icon: <BookOpen size={14} />,
      },
      { title: "Getting started", href: "/documentation/getting-started", icon: <Zap size={14} /> },
      { title: "Product overview", href: "/documentation/features", icon: <Layers3 size={14} /> },
    ],
  },
  {
    group: "Documents Hub",
    items: [
      {
        title: "Documents Hub",
        href: "/documentation/documents-hub",
        icon: <FileStack size={14} />,
      },
      {
        title: "Organization & collaboration",
        href: "/documentation/document-organization",
        icon: <FolderKanban size={14} />,
      },
    ],
  },
  {
    group: "Query",
    items: [
      {
        title: "Grounded queries",
        href: "/documentation/grounded-query",
        icon: <Search size={14} />,
      },
    ],
  },
  {
    group: "DeepSpace",
    items: [
      {
        title: "DeepSpace workspace",
        href: "/documentation/deepspace",
        icon: <Sparkles size={14} />,
      },
      {
        title: "DeepSpace Library",
        href: "/documentation/deepspace-library",
        icon: <Boxes size={14} />,
      },
      {
        title: "Notes & editor",
        href: "/documentation/editor-files",
        icon: <BookOpen size={14} />,
      },
      { title: "Web research", href: "/documentation/web-research", icon: <Network size={14} /> },
      {
        title: "Sandbox & data analysis",
        href: "/documentation/sandbox",
        icon: <Layers3 size={14} />,
      },
      {
        title: "Artifacts & exports",
        href: "/documentation/artifacts",
        icon: <FileStack size={14} />,
      },
      {
        title: "Schedules & automation",
        href: "/documentation/automation",
        icon: <CalendarClock size={14} />,
      },
      { title: "Memory", href: "/documentation/memory-workspace", icon: <Layers3 size={14} /> },
      { title: "Voice", href: "/documentation/voice", icon: <Waypoints size={14} /> },
    ],
  },
  {
    group: "Collections & sharing",
    items: [
      {
        title: "Collections",
        href: "/documentation/collections-sharing",
        icon: <FolderKanban size={14} />,
      },
    ],
  },
  {
    group: "Providers & connections",
    items: [
      { title: "AI providers", href: "/documentation/providers", icon: <Network size={14} /> },
      {
        title: "MCP connectors",
        href: "/documentation/connectors-mcp",
        icon: <Waypoints size={14} />,
      },
    ],
  },
  {
    group: "Account, trust & settings",
    items: [
      { title: "Profile & sessions", href: "/documentation/profile", icon: <Settings size={14} /> },
      {
        title: "Plans, storage & settings",
        href: "/documentation/workspace-settings",
        icon: <Settings size={14} />,
      },
      { title: "Notifications", href: "/documentation/notifications", icon: <Zap size={14} /> },
      {
        title: "Privacy & security",
        href: "/documentation/privacy-security",
        icon: <Shield size={14} />,
      },
    ],
  },
  {
    group: "Help & feedback",
    items: [
      { title: "Support centre", href: "/documentation/support", icon: <HelpCircle size={14} /> },
      {
        title: "Share feedback",
        href: "/documentation/feedback",
        icon: <HeartHandshake size={14} />,
      },
      { title: "Release notes & roadmap", href: "/documentation/roadmap", icon: <Zap size={14} /> },
    ],
  },
  {
    group: "Technical reference",
    items: [
      {
        title: "Architecture overview",
        href: "/documentation/architecture",
        icon: <Layers3 size={14} />,
      },
      {
        title: "System walkthrough",
        href: "/documentation/simple-system-walkthrough",
        icon: <BookOpen size={14} />,
      },
    ],
  },
];

export const docsNav: NavItem[] = docsNavGroups.flatMap(({ items }) =>
  items.flatMap((item) => (item.items ? [item, ...item.items] : [item])),
);
