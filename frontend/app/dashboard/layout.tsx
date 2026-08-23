"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  FileText,
  ShieldAlert,
  Settings as SettingsIcon,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  Database,
  Search as SearchIcon,
  Sun,
  Moon,
  User,
  Activity,
  FolderKanban,
  PanelsLeftBottom,
  LifeBuoy,
  Sparkles,
  Trash2,
  Cable,
  X,
} from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import AuthGuard from "@/app/components/layout/AuthGuard";
import NotificationCenter from "@/app/components/layout/NotificationCenter";
import AverQelLogo from "@/app/components/ui/AverQelLogo";
import { APP_VERSION } from "@/lib/release";
import Breadcrumbs from "@/app/components/ui/Breadcrumbs";
import SystemStatus from "@/app/components/dashboard/SystemStatus";
import { getRoleLabel, hasAdminRole } from "@/lib/roles";
import DisabledOverlay from "@/app/components/auth/DisabledOverlay";

type NavLeaf = {
  name: string;
  href: string;
  icon: React.ReactNode;
  exact?: boolean;
  isHeader?: false;
  admin?: boolean;
};
type NavHeader = {
  name: string;
  href: string;
  isHeader: true;
  admin?: boolean;
  items: NavLeaf[];
};
type NavItem = NavLeaf | NavHeader;

const BASE_NAV_ITEMS: NavItem[] = [
  { name: "Dashboard", href: "/dashboard", icon: <LayoutDashboard size={18} />, exact: true },
  { name: "Documents Hub", href: "/dashboard/documents", icon: <FileText size={18} /> },
  { name: "Query", href: "/dashboard/query", icon: <SearchIcon size={18} /> },
  { name: "Collections", href: "/dashboard/collections", icon: <FolderKanban size={18} /> },
  { name: "MCP Servers", href: "/dashboard/mcp", icon: <Cable size={18} /> },
  { name: "DeepSpace", href: "/dashboard/deepspace", icon: <PanelsLeftBottom size={18} /> },

  {
    name: "Admin",
    href: "#",
    isHeader: true,
    admin: true,
    items: [
      {
        name: "Users",
        href: "/dashboard/admin/users",
        icon: <User size={18} />,
      },
      {
        name: "Workspaces",
        href: "/dashboard/admin/tenants",
        icon: <Database size={18} />,
      },
      { name: "Audit Logs", href: "/dashboard/admin/audit-logs", icon: <ShieldAlert size={18} /> },
      { name: "Analytics", href: "/dashboard/admin/analytics", icon: <Activity size={18} /> },
      {
        name: "Support Management",
        href: "/dashboard/admin/support",
        icon: <LifeBuoy size={18} />,
        admin: true,
      },
      {
        name: "Feedback Management",
        href: "/dashboard/admin/feedback",
        icon: <Sparkles size={18} />,
        admin: true,
      },

      { name: "Data Deletion", href: "/dashboard/admin/deletion", icon: <Trash2 size={18} /> },

      { name: "System Metrics", href: "/dashboard/admin/metrics", icon: <Activity size={18} /> },
    ],
  },
  {
    name: "Settings",
    href: "#",
    isHeader: true,
    items: [
      { name: "Global Settings", href: "/dashboard/settings", icon: <SettingsIcon size={18} /> },
      { name: "Support | Help", href: "/dashboard/support", icon: <LifeBuoy size={18} /> },
      { name: "Share Feedback", href: "/dashboard/feedback", icon: <Sparkles size={18} /> },
    ],
  },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, loading: authLoading, userDisabled } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navContainerRef = useRef<HTMLDivElement>(null);
  const mainContentRef = useRef<HTMLDivElement>(null);

  const isAdminRoute = pathname.startsWith("/dashboard/admin");
  const isQueryRoute = pathname === "/dashboard/query";
  const isDeepSpaceRoute =
    pathname === "/dashboard/deepspace" || pathname.startsWith("/dashboard/deepspace/");
  const isCollectionsRoute = pathname.includes("/collections");
  const isFullHeightRoute = isQueryRoute || isDeepSpaceRoute || isCollectionsRoute;
  const hasAdminAccess = user ? hasAdminRole(user.roles) : false;

  const navItems = useMemo(() => {
    return BASE_NAV_ITEMS.filter((item) => {
      if (item.admin && !hasAdminAccess) return false;
      return true;
    });
  }, [hasAdminAccess]);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      if (mobile) {
        setSidebarOpen(false);
      } else {
        setSidebarOpen(true);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    document.documentElement.toggleAttribute("data-dashboard-nav-open", isMobile && mobileMenuOpen);

    return () => {
      document.documentElement.removeAttribute("data-dashboard-nav-open");
    };
  }, [isMobile, mobileMenuOpen]);

  const shouldShowDisabledOverlay = userDisabled;

  if (authLoading) return null;

  const NavLink = ({ item, onClick }: { item: NavLeaf; onClick?: () => void }) => {
    // Improved active check: exact match for home, startsWith for others but avoid overlaps
    const isActive = item.exact
      ? pathname === item.href
      : pathname.startsWith(item.href) && (item.href !== "/dashboard" || pathname === "/dashboard");

    return (
      <Link
        href={item.href}
        prefetch={false}
        data-active={isActive}
        onClick={onClick}
        className={`group sweeping-light-btn relative flex h-11 items-center overflow-hidden rounded-xl transition-all duration-200 ${
          isActive
            ? "text-primary shadow-sm"
            : "text-foreground/60 hover:bg-foreground/[0.04] hover:text-foreground"
        } ${!sidebarOpen && !isMobile ? "justify-center px-0" : ""}`}
      >
        <motion.div
          className={`relative z-10 flex h-full w-full items-center ${!sidebarOpen && !isMobile ? "justify-center gap-0 px-0" : "gap-3 px-3"}`}
          whileTap={{ scale: 0.96 }}
          transition={{ type: "spring", stiffness: 450, damping: 26 }}
        >
          {/* Left Indicator - Premium Sliding Bar */}
          {isActive && (
            <motion.div
              layoutId="active-nav-indicator"
              className={`bg-primary absolute left-0 rounded-r-full ${
                !sidebarOpen && !isMobile ? "h-6 w-[3px]" : "h-5 w-[3px]"
              }`}
              transition={{ type: "spring", stiffness: 380, damping: 30 }}
            />
          )}

          <div
            className={`shrink-0 transition-transform duration-200 ${isActive ? "scale-110" : "group-hover:scale-110"}`}
          >
            {item.icon}
          </div>
          {(sidebarOpen || isMobile) && (
            <span
              className={`truncate text-sm font-bold tracking-tight ${isActive ? "" : "font-medium"}`}
            >
              {item.name}
            </span>
          )}
        </motion.div>

        {/* Sliding Background Pill */}
        {isActive && (
          <motion.div
            layoutId="active-nav-pill"
            className="bg-primary/10 absolute inset-0 z-0 rounded-xl"
            transition={{ type: "spring", stiffness: 380, damping: 30 }}
          />
        )}
      </Link>
    );
  };

  const renderSidebarContent = () => (
    <>
      <div
        className={`flex h-18 items-center px-4 pt-2 ${!sidebarOpen && !isMobile ? "justify-center px-0" : "justify-between"}`}
      >
        <AverQelLogo size="nav" showWordmark={sidebarOpen || isMobile} />
        {(sidebarOpen || isMobile) && isMobile && (
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={20} />
          </button>
        )}
      </div>

      <nav
        ref={navContainerRef}
        className="relative flex-1 space-y-2 overflow-x-hidden overflow-y-auto p-3"
      >
        {navItems.map((item, idx) => {
          if (item.admin && !hasAdminAccess) return null;

          if (item.isHeader) {
            return (
              <div key={`header-${idx}`} className="pt-4 pb-1">
                {(sidebarOpen || isMobile) && (
                  <p className="text-muted-foreground mb-1.5 px-3 text-[10px] font-black tracking-[0.22em] uppercase">
                    {item.name}
                  </p>
                )}
                <div className="space-y-1">
                  {item.items
                    .filter((sub) => !sub.admin || hasAdminAccess)
                    .map((subItem) => (
                      <NavLink
                        key={subItem.href}
                        item={subItem}
                        onClick={() => isMobile && setMobileMenuOpen(false)}
                      />
                    ))}
                </div>
              </div>
            );
          }

          return (
            <NavLink
              key={item.href}
              item={item as NavLeaf}
              onClick={() => isMobile && setMobileMenuOpen(false)}
            />
          );
        })}
      </nav>

      {!isMobile && (
        <div
          className={`space-y-2 p-3 ${pathname === "/dashboard/query" ? "" : "border-glass-border border-t"}`}
        >
          <motion.button
            onClick={() => setSidebarOpen((prev) => !prev)}
            className={`ui-btn btn-ghost sweeping-light-btn h-12 ${sidebarOpen ? "w-full justify-start gap-2 px-4" : "border-glass-border bg-surface-1/40 w-full justify-center rounded-2xl shadow-xl"}`}
            aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            whileTap={{ scale: 0.96 }}
          >
            <motion.span
              initial={false}
              animate={{ rotate: sidebarOpen ? 0 : 180 }}
              transition={{ type: "spring", stiffness: 420, damping: 30 }}
            >
              {sidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
            </motion.span>
            {sidebarOpen && <span className="text-sm font-bold">Collapse</span>}
          </motion.button>
          {sidebarOpen && (
            <div className="bg-primary/5 border-primary/10 text-primary/70 flex items-center justify-center rounded-full border px-2 py-1 text-[10px] font-bold tracking-[0.14em] uppercase">
              {APP_VERSION}
              {process.env.NEXT_PUBLIC_GIT_SHA && process.env.NEXT_PUBLIC_GIT_SHA !== "unknown" ? ` • ${String(process.env.NEXT_PUBLIC_GIT_SHA).slice(0, 7)}` : ""}
            </div>
          )}
        </div>
      )}
    </>
  );

  const renderRestrictedContent = (options: { title: string; body: string; chip: string }) => (
    <div className="mx-auto max-w-3xl space-y-6 px-2 py-8">
      <div className="theme-panel rounded-[1.5rem] p-8">
        <div className="theme-accent-pill inline-flex items-center gap-2 rounded-full px-3 py-1 text-[10px] font-semibold tracking-[0.2em] uppercase">
          <ShieldAlert size={12} />

          {options.chip}
        </div>
        <h1 className="text-foreground mt-5 text-3xl font-semibold tracking-tight">
          {options.title}
        </h1>
        <p className="text-muted-foreground mt-3 max-w-2xl text-sm leading-7">{options.body}</p>
      </div>
    </div>
  );

  return (
    <AuthGuard>
      <div className="app-shell-grid text-foreground flex h-[100svh] overflow-hidden font-sans">
        {!isMobile && (
          <motion.aside
            initial={false}
            animate={{ width: sidebarOpen ? 256 : 84 }}
            transition={{ type: "spring", stiffness: 280, damping: 28, mass: 0.9 }}
            className="card-elevated relative z-20 my-4 mr-3 ml-4 flex h-[calc(100svh-2rem)] flex-col rounded-l-xl rounded-r-2xl border-r-0"
          >
            {renderSidebarContent()}
          </motion.aside>
        )}

        <AnimatePresence>
          {isMobile && mobileMenuOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setMobileMenuOpen(false)}
                className="bg-background/80 fixed inset-0 z-40 backdrop-blur-sm"
                style={{ position: "fixed" }}
              />
              <motion.aside
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ type: "tween", duration: 0.22, ease: "easeOut" }}
                className="card-elevated fixed top-2 bottom-2 left-2 z-50 flex w-[min(18rem,calc(100vw-1rem))] flex-col overflow-visible rounded-l-xl rounded-r-2xl border-r-0"
                style={{ position: "fixed", overflow: "visible" }}
              >
                {renderSidebarContent()}
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        <div
          className={`relative my-2 flex h-[calc(100svh-1rem)] min-w-0 flex-1 flex-col overflow-hidden sm:my-4 sm:h-[calc(100svh-2rem)] ${isMobile ? "mx-2" : "mr-3"}`}
        >
          <header className="border-glass-border bg-glass-bg/75 relative z-20 flex min-h-16 flex-nowrap items-center justify-between gap-3 overflow-visible rounded-2xl border px-3 py-3 backdrop-blur-md sm:backdrop-blur-xl md:min-h-18 md:px-6">
            <div className="relative z-10 flex min-w-0 flex-nowrap items-center gap-3">
              {isMobile && (
                <button
                  onClick={() => setMobileMenuOpen(true)}
                  className="border-glass-border bg-muted text-muted-foreground hover:text-foreground inline-flex h-10 w-10 items-center justify-center rounded-xl border transition-all active:scale-95"
                  aria-label="Open menu"
                >
                  <Menu size={20} />
                </button>
              )}

              <div className="hidden min-w-0 flex-col gap-0.5 sm:flex">
                <Breadcrumbs />
              </div>

              {isMobile && (
                <div
                  className={`origin-left scale-[0.58] ${isDeepSpaceRoute ? "hidden sm:block" : ""}`}
                >
                  <AverQelLogo size="nav" showWordmark={false} disableAnimation />
                </div>
              )}
            </div>

            {/* Center portal target for Deepspace layout controls */}
            <div
              id="header-layout-controls"
              className="mx-1 flex flex-1 items-center justify-center empty:hidden sm:mx-4"
            />

            <div className="relative z-10 flex items-center justify-end gap-1.5 md:gap-3">
              <div className="hidden sm:block">
                <SystemStatus />
              </div>
              <NotificationCenter />

              <button
                onClick={toggleTheme}
                data-tooltip={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
                className={`ui-tooltip bg-muted border-glass-border text-muted-foreground hover:text-foreground inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-all hover:-translate-y-0.5 hover:shadow-md ${isDeepSpaceRoute ? "hidden sm:inline-flex" : ""}`}
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>

              <div className="bg-glass-border hidden h-5 w-px sm:block" />

              <div className="hidden flex-col items-end lg:flex">
                <span className="text-foreground max-w-[12rem] truncate text-sm font-black">
                  {user?.email}
                </span>
                <span className="text-primary text-[10px] font-black tracking-[0.18em] uppercase">
                  {user?.roles[0] ? getRoleLabel(user.roles[0]) : ""}
                </span>
              </div>

              <div
                className={`border-primary/35 bg-primary/15 text-primary flex h-9 w-9 items-center justify-center rounded-full border text-sm font-bold ${isDeepSpaceRoute ? "hidden sm:flex" : ""}`}
              >
                {user?.email?.[0].toUpperCase()}
              </div>

              <button
                onClick={logout}
                data-tooltip="Logout"
                className={`ui-tooltip bg-muted border-glass-border text-muted-foreground inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-sm transition-all hover:-translate-y-0.5 hover:border-red-500/40 hover:text-red-500 hover:shadow-md ${isDeepSpaceRoute ? "hidden sm:inline-flex" : ""}`}
                aria-label="Logout"
              >
                <LogOut size={15} />
                <span className="hidden font-bold lg:inline">Logout</span>
              </button>
            </div>
          </header>

          <main
            ref={mainContentRef}
            className={`dashboard-main-surface flex-1 overflow-x-hidden ${
              isFullHeightRoute && !isMobile ? "overflow-y-hidden" : "overflow-y-auto"
            } ${
              isQueryRoute || isDeepSpaceRoute
                ? "px-0 pt-3 pb-0 sm:pt-4"
                : "px-3 pt-3 pb-4 sm:px-6 sm:pt-4"
            }`}
          >
            <div className={isFullHeightRoute ? "flex h-full min-h-0 w-full flex-col" : "w-full"}>
              {isAdminRoute && !hasAdminAccess
                ? renderRestrictedContent({
                    title: "Admin Console Restricted",
                    body: "This area is reserved for admins. Normal users can continue using documents, query, collections, profile, and trust/privacy settings.",
                    chip: "Admin Only",
                  })
                : children}
            </div>
          </main>
        </div>
        <DisabledOverlay isVisible={shouldShowDisabledOverlay} />
      </div>
    </AuthGuard>
  );
}
