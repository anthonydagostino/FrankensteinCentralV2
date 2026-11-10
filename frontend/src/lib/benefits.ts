import type { BenefitOut, BenefitStatus } from "../api/types";
import type { ChipTone } from "../components/Bars";
import { toNumber } from "./format";

const STATUS_ORDER: Record<BenefitStatus, number> = { pending: 1, unused: 2, manual: 2, partial: 3, used: 4, expired_unused: 5, expired_partial: 5 };
const STATUS_LABEL: Record<BenefitStatus, string> = {
  used: "Used",
  partial: "Partial",
  pending: "Pending",
  unused: "Unused",
  expired_unused: "Expired",
  expired_partial: "Expired, partial",
  manual: "Mark by hand",
};

/** Expiring soon first, then pending, unused, partial, used; ties broken by the larger remaining amount. */
export function sortBenefits(list: BenefitOut[]): BenefitOut[] {
  return [...list].sort((a, b) => {
    const ca = a.current;
    const cb = b.current;
    if (!ca && !cb) return 0;
    if (!ca) return 1;
    if (!cb) return -1;
    if (ca.expiring_soon !== cb.expiring_soon) return ca.expiring_soon ? -1 : 1;
    if (STATUS_ORDER[ca.status] !== STATUS_ORDER[cb.status]) return STATUS_ORDER[ca.status] - STATUS_ORDER[cb.status];
    return toNumber(cb.remaining) - toNumber(ca.remaining);
  });
}

export function statusTone(status: BenefitStatus): ChipTone {
  if (status === "used") return "good";
  if (status === "pending") return "warn";
  if (status === "partial") return "info";
  if (status.startsWith("expired")) return "bad";
  return "neutral";
}

export const statusLabel = (status: BenefitStatus): string => STATUS_LABEL[status];
