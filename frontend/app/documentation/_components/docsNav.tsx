import { ReactNode } from "react";
import {
  BookOpen,
  Layers3,
  Network,
  Shield,
  Zap,
  Home,
  Settings,
  HelpCircle,
  HeartHandshake,
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

export const docsNavGroups: NavGroup[] = [
  {
    group: "Core Concept",
    items: [
      { title: "Home", href: "/documentation", icon: <Home size={14} /> },
      { title: "Getting Started", href: "/documentation/getting-started", icon: <Zap size={14} /> },
      {
        title: "What Is AverQel",
        href: "/documentation/what-is-averqel",
        icon: <BookOpen size={14} />,
      },
    ],
  },
  {
    group: "Platform Features",
    items: [
      { title: "Documents Hub", href: "/documentation/editor-files", icon: <BookOpen size={14} /> },
      {
        title: "Grounded Queries",
        href: "/documentation/grounded-query",
        icon: <BookOpen size={14} />,
      },
      {
        title: "Collections & Sharing",
        href: "/documentation/collections-sharing",
        icon: <BookOpen size={14} />,
      },
      {
        title: "Connectors & MCP",
        href: "/documentation/connectors-mcp",
        icon: <Network size={14} />,
      },
      {
        title: "Memory & Workspace",
        href: "/documentation/memory-workspace",
        icon: <Layers3 size={14} />,
      },
    ],
  },
  {
    group: "Control & Security",
    items: [
      {
        title: "Privacy & Security",
        href: "/documentation/privacy-security",
        icon: <Shield size={14} />,
      },
      { title: "Platform Admin", href: "/documentation/admin", icon: <Shield size={14} /> },
    ],
  },
  {
    group: "Global Settings",
    items: [
      { title: "Profile Settings", href: "/documentation/profile", icon: <Settings size={14} /> },
      {
        title: "Trust & Privacy",
        href: "/documentation/privacy-security",
        icon: <Shield size={14} />,
      },
      {
        title: "Autonomous Memory",
        href: "/documentation/memory-workspace",
        icon: <Layers3 size={14} />,
      },
      { title: "Providers Config", href: "/documentation/providers", icon: <Network size={14} /> },
    ],
  },
  {
    group: "Help & Feedback",
    items: [
      { title: "Support Centre", href: "/documentation/support", icon: <HelpCircle size={14} /> },
      {
        title: "Share Feedback",
        href: "/documentation/feedback",
        icon: <HeartHandshake size={14} />,
      },
      { title: "Product Roadmap", href: "/documentation/roadmap", icon: <Zap size={14} /> },
    ],
  },
  {
    group: "Developer Resource",
    items: [
      {
        title: "Architecture Spec",
        href: "/documentation/architecture",
        icon: <Layers3 size={14} />,
      },
      {
        title: "System Walkthrough",
        href: "/documentation/simple-system-walkthrough",
        icon: <BookOpen size={14} />,
      },
    ],
  },
];

export const docsNav: NavItem[] = docsNavGroups.flatMap((g) => {
  return g.items.flatMap((item) => {
    if (item.items) {
      return [item, ...item.items];
    }
    return [item];
  });
});
