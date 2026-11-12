/**
 * The wall behind the cards: the palette's slow turn of colour (CSS, tokens.css) and, over it, a swirl
 * engraved in hairlines. Each ring is the one before it, a little larger and turned a few degrees, so the
 * set reads as one slow turn. Drawn in the text colour at a few percent: it is felt more than seen.
 */
const RINGS = Array.from({ length: 13 }, (_, i) => ({
  rx: 90 + i * 58,
  ry: 54 + i * 37,
  turn: -18 + i * 6.5,
}));

export function Wall() {
  return (
    <svg className="lf-wall" viewBox="0 0 1280 800" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <g className="lf-wall__swirl" fill="none" strokeWidth="1">
        {RINGS.map((r) => (
          <ellipse key={r.rx} cx="0" cy="0" rx={r.rx} ry={r.ry} transform={`rotate(${r.turn})`} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
    </svg>
  );
}
