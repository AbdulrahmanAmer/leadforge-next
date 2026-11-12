/**
 * The LeadForge mark: an ingot on an anvil. Lead is the metal as well as the contact, and a forge
 * is where a rough bar becomes something usable.
 * Drawn on a 32 grid with every edge on an even unit, so at 16 px each edge lands on a whole pixel.
 * `tile` puts it on the accent (the app mark); without it the mark is one colour, `currentColor`.
 */
export function Logo({ size = 32, tile = false, title = "LeadForge" }: { size?: number; tile?: boolean; title?: string }) {
  return (
    <svg className={tile ? "lf-logo lf-logo--tile" : "lf-logo"} width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={title}>
      <title>{title}</title>
      {tile && <rect className="lf-logo__tile" width="32" height="32" rx="8" />}
      <g className="lf-logo__mark" transform={tile ? "translate(4 6) scale(0.75)" : "translate(0 2)"}>
        <path className="lf-logo__ingot" d="M12 2h8l2 4H10z" />
        <path className="lf-logo__anvil" d="M2 8h26v4h-5c-2 0-3 2-3 4v4h4v4H8v-4h4v-4c0-2-2-4-4-4-3 0-5-1.5-6-4z" />
      </g>
    </svg>
  );
}
