import {
  AlertTriangle, BadgeDollarSign, Calendar, CalendarCheck, CalendarClock, CircleHelp, Cloud, CloudDrizzle, CloudFog, CloudHail, CloudLightning, CloudMoon, CloudRain, CloudRainWind, CloudSnow, CloudSun,
  Container, Database, DatabaseBackup, DatabaseZap, HeartPulse, KeyRound, Link, Moon, Receipt, ShieldOff, Sun, Tv, Umbrella, Wallet, Wind, Snowflake, SunMedium, type LucideIcon,
} from "lucide-react";

const MAP: Record<string, LucideIcon> = {
  sun: Sun,
  moon: Moon,
  cloud: Cloud,
  "cloud-sun": CloudSun,
  "cloud-moon": CloudMoon,
  "cloud-fog": CloudFog,
  "cloud-drizzle": CloudDrizzle,
  "cloud-rain": CloudRain,
  "cloud-hail": CloudHail,
  "cloud-snow": CloudSnow,
  "cloud-rain-wind": CloudRainWind,
  "cloud-lightning": CloudLightning,
  "cloud-alert": CloudLightning,
  "triangle-alert": AlertTriangle,
  umbrella: Umbrella,
  wind: Wind,
  freeze: Snowflake,
  uv: SunMedium,
  "shield-off": ShieldOff,
  "database-backup": DatabaseBackup,
  "database-zap": DatabaseZap,
  database: Database,
  container: Container,
  "heart-pulse": HeartPulse,
  "badge-dollar-sign": BadgeDollarSign,
  "circle-help": CircleHelp,
  "calendar-clock": CalendarClock,
  "calendar-check": CalendarCheck,
  calendar: Calendar,
  wallet: Wallet,
  tv: Tv,
  "key-round": KeyRound,
  receipt: Receipt,
  link: Link,
};

export function iconFor(name: string | null | undefined): LucideIcon {
  if (!name) return Cloud;
  return MAP[name] ?? Link;
}

export function DynamicIcon({ name, className, size }: { name: string | null | undefined; className?: string; size?: number }) {
  const Icon = iconFor(name);
  return <Icon className={className} size={size} aria-hidden="true" />;
}
