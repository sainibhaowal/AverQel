import {
  BarChart3,
  Building2,
  CalendarDays,
  Check,
  Clock3,
  Cloud,
  Code2,
  Compass,
  Database,
  Globe,
  Heart,
  Info,
  Landmark,
  Layers,
  Lightbulb,
  Mail,
  MapPin,
  Phone,
  Shield,
  Sparkles,
  Star,
  Target,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { VisualIconName } from "../_lib/stream-protocol";

const icons: Record<VisualIconName, LucideIcon> = {
  sparkles: Sparkles,
  lightbulb: Lightbulb,
  target: Target,
  shield: Shield,
  layers: Layers,
  zap: Zap,
  globe: Globe,
  chart: BarChart3,
  check: Check,
  clock: Clock3,
  "map-pin": MapPin,
  building: Building2,
  users: Users,
  database: Database,
  cloud: Cloud,
  code: Code2,
  star: Star,
  heart: Heart,
  phone: Phone,
  calendar: CalendarDays,
  landmark: Landmark,
  compass: Compass,
  info: Info,
};

const themeCardSurfaceClasses = "border-glass-border bg-surface-0 dark:bg-surface-1";
export const visualCardToneClasses = {
  info: themeCardSurfaceClasses,
  success: themeCardSurfaceClasses,
  warning: themeCardSurfaceClasses,
  error: themeCardSurfaceClasses,
  neutral: themeCardSurfaceClasses,
} as const;

export const visualCardDetailSurfaceClasses =
  "border-glass-border bg-surface-1 dark:bg-surface-2";

export const visualIconBadgeClasses =
  "border-glass-border bg-surface-1 text-foreground dark:bg-surface-2";

export function DetailVisualIcon({
  name,
  label,
  size = 16,
}: {
  name?: VisualIconName | null;
  label: string;
  size?: number;
}) {
  const normalizedLabel = label.toLowerCase();
  const FallbackIcon =
    /\b(address|location|place|venue)\b/.test(normalizedLabel)
      ? MapPin
      : /\b(hours?|time|schedule|open|close)\b/.test(normalizedLabel)
        ? Clock3
        : /\b(email|e-mail|mail)\b/.test(normalizedLabel)
          ? Mail
          : /\b(phone|call|telephone)\b/.test(normalizedLabel)
            ? Phone
            : /\b(website|url|source|link)\b/.test(normalizedLabel)
              ? Globe
              : Info;
  const Icon = isVisualIconName(name) ? icons[name] : FallbackIcon;

  return <Icon size={size} aria-hidden="true" />;
}

export default function VisualIcon({
  name,
  size = 18,
  className,
}: {
  name?: VisualIconName | null;
  size?: number;
  className?: string;
}) {
  const Icon = isVisualIconName(name) ? icons[name] : Info;
  return <Icon size={size} className={className} aria-hidden="true" />;
}

export function isVisualIconName(value: unknown): value is VisualIconName {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(icons, value);
}
