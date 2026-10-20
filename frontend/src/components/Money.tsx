import { formatMoney } from "../lib/format";
import { usePrivacy } from "../lib/privacy";

export function Money({ value, whole, sign, className = "", href }: { value: string | number | null | undefined; whole?: boolean; sign?: boolean; className?: string; href?: string | null }) {
  const { blurred } = usePrivacy();
  const text = formatMoney(value, { whole, sign });
  const inner = <span className={`tabular ${blurred ? "privacy-blur" : ""} ${className}`}>{text}</span>;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="hover:underline">
        {inner}
      </a>
    );
  }
  return inner;
}
