import { formatMoney } from "../lib/format";
import { usePrivacy } from "../lib/privacyContext";

/**
 * A dollar amount that honors the privacy toggle.
 * `open` amounts never blur (card benefit credits are not private: they are the card's terms, not a balance).
 * `strong` amounts blur harder (net worth is the one number that should be unreadable from across a room).
 */
export function Money({
  value,
  whole,
  sign,
  className = "",
  href,
  open = false,
  strong = false,
}: {
  value: string | number | null | undefined;
  whole?: boolean;
  sign?: boolean;
  className?: string;
  href?: string | null;
  open?: boolean;
  strong?: boolean;
}) {
  const { blurred } = usePrivacy();
  const text = formatMoney(value, { whole, sign });
  const blur = blurred && !open ? (strong ? "privacy-blur privacy-blur-strong" : "privacy-blur") : "";
  const inner = <span className={`tabular ${blur} ${className}`}>{text}</span>;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="hover:underline">
        {inner}
      </a>
    );
  }
  return inner;
}
