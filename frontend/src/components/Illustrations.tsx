/**
 * Flat vector illustrations drawn inline so they scale crisply and follow the app palette.
 * Colours come from CSS variables with fallbacks: --ill-1 navy, --ill-2 blue, --ill-3 light blue,
 * --ill-4 pale, --ill-accent amber, --ill-ink text.
 */
import type { SVGProps } from "react";

const NAVY = "var(--ill-1, #104281)";
const BLUE = "var(--ill-2, #2a78d6)";
const LIGHT = "var(--ill-3, #86b6ef)";
const PALE = "var(--ill-4, #e3ecf8)";
const AMBER = "var(--ill-accent, #fab219)";
const INK = "var(--ill-ink, #121826)";
const WHITE = "#ffffff";
const GOOD = "var(--good, #0ca30c)";
const RED = "var(--critical, #d03b3b)";

type Props = SVGProps<SVGSVGElement> & { title?: string };

function Svg({ title, children, ...rest }: Props & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 240 160" role="img" aria-label={title} xmlns="http://www.w3.org/2000/svg" {...rest}>
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

function Person({ x, y, s = 1, color = NAVY, badge }: { x: number | string; y: number | string; s?: number; color?: string; badge?: string }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle cx="0" cy="-14" r="7" fill={color} />
      <path d="M-11 12 a11 11 0 0 1 22 0 v4 h-22z" fill={color} />
      {badge ? <circle cx="9" cy="-16" r="4" fill={badge} stroke={WHITE} strokeWidth="1.5" /> : null}
    </g>
  );
}

/** Three data sources flowing into one store. */
export function DataInArt(props: Props) {
  const card = (x: number, y: number) => (
    <g>
      <rect x={x} y={y} width="54" height="38" rx="5" fill={WHITE} stroke={LIGHT} strokeWidth="2" />
      <rect x={x + 8} y={y + 8} width="24" height="4" rx="2" fill={NAVY} />
      <rect x={x + 8} y={y + 17} width="38" height="3" rx="1.5" fill={LIGHT} />
      <rect x={x + 8} y={y + 25} width="30" height="3" rx="1.5" fill={LIGHT} />
    </g>
  );
  return (
    <Svg title="Orders, profiles and outcomes flowing into one data store" {...props}>
      <circle cx="178" cy="82" r="58" fill={PALE} />
      {card(14, 18)}
      {card(14, 62)}
      {card(14, 106)}
      <path d="M72 37 C110 37 110 82 140 82" fill="none" stroke={BLUE} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M72 81 C100 81 110 82 140 82" fill="none" stroke={BLUE} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M72 125 C110 125 110 82 140 82" fill="none" stroke={BLUE} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M134 76 l8 6 l-8 6" fill="none" stroke={BLUE} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <g>
        <ellipse cx="180" cy="54" rx="30" ry="10" fill={NAVY} />
        <rect x="150" y="54" width="60" height="52" fill={NAVY} />
        <ellipse cx="180" cy="106" rx="30" ry="10" fill={NAVY} />
        <ellipse cx="180" cy="54" rx="30" ry="10" fill={BLUE} />
        <path d="M150 72 a30 10 0 0 0 60 0" fill="none" stroke={LIGHT} strokeWidth="2" />
        <path d="M150 88 a30 10 0 0 0 60 0" fill="none" stroke={LIGHT} strokeWidth="2" />
      </g>
      <circle cx="222" cy="40" r="4" fill={AMBER} />
      <circle cx="212" cy="26" r="2.5" fill={AMBER} />
    </Svg>
  );
}

/** Methods compete on a podium; the winner is checked. */
export function CompeteArt(props: Props) {
  return (
    <Svg title="Several prediction methods compete and the most accurate wins" {...props}>
      <circle cx="120" cy="84" r="64" fill={PALE} />
      <rect x="50" y="96" width="44" height="40" rx="4" fill={LIGHT} />
      <rect x="98" y="62" width="44" height="74" rx="4" fill={NAVY} />
      <rect x="146" y="110" width="44" height="26" rx="4" fill={BLUE} />
      <text x="72" y="122" textAnchor="middle" fontSize="14" fontWeight="700" fill={WHITE} fontFamily="sans-serif">
        2
      </text>
      <text x="120" y="104" textAnchor="middle" fontSize="18" fontWeight="700" fill={WHITE} fontFamily="sans-serif">
        1
      </text>
      <text x="168" y="130" textAnchor="middle" fontSize="12" fontWeight="700" fill={WHITE} fontFamily="sans-serif">
        3
      </text>
      <circle cx="72" cy="82" r="10" fill={BLUE} />
      <circle cx="120" cy="40" r="12" fill={AMBER} />
      <path d="M113 40 l5 5 l10 -10" fill="none" stroke={WHITE} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="168" cy="96" r="9" fill={LIGHT} />
      <rect x="40" y="140" width="160" height="4" rx="2" fill={LIGHT} />
    </Svg>
  );
}

/** One engine in the middle, many business questions around it. */
export function UniversalArt(props: Props) {
  const spoke = (x: number, y: number, icon: React.ReactNode) => (
    <g>
      <line x1="120" y1="80" x2={x} y2={y} stroke={LIGHT} strokeWidth="2.5" />
      <circle cx={x} cy={y} r="17" fill={WHITE} stroke={LIGHT} strokeWidth="2" />
      <g transform={`translate(${x} ${y})`}>{icon}</g>
    </g>
  );
  return (
    <Svg title="One detection engine connected to many business questions" {...props}>
      {spoke(44, 36, <rect x="-7" y="-6" width="14" height="12" rx="2" fill={NAVY} />)}
      {spoke(196, 36, <path d="M-8 4 h10 v-8 h4 l4 5 v3 h-18z" fill={NAVY} />)}
      {spoke(28, 100, <path d="M-7 -6 h9 l5 5 v8 h-14z" fill={NAVY} />)}
      {spoke(212, 100, <path d="M-8 6 l5 -8 l4 4 l6 -9" fill="none" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />)}
      {spoke(64, 140, <path d="M-8 -6 h16 l-2 12 h-12z" fill={NAVY} />)}
      {spoke(176, 140, <circle cx="0" cy="0" r="6" fill="none" stroke={NAVY} strokeWidth="2.5" />)}
      <rect x="88" y="48" width="64" height="64" rx="14" fill={NAVY} />
      <circle cx="120" cy="80" r="16" fill="none" stroke={WHITE} strokeWidth="3" />
      <circle cx="120" cy="80" r="5" fill={AMBER} />
      {[0, 60, 120, 180, 240, 300].map((a) => (
        <rect key={a} x="118" y="56" width="4" height="8" rx="2" fill={WHITE} transform={`rotate(${a} 120 80)`} />
      ))}
    </Svg>
  );
}

/** Three milestones on a path to a flag. */
export function RoadmapArt(props: Props) {
  return (
    <Svg title="A three-step path to going live" {...props}>
      <path d="M20 120 C 70 120, 70 60, 120 60 S 170 120, 220 50" fill="none" stroke={LIGHT} strokeWidth="6" strokeLinecap="round" />
      {[
        { x: 40, y: 118, n: "1", c: NAVY },
        { x: 120, y: 60, n: "2", c: BLUE },
        { x: 190, y: 92, n: "3", c: LIGHT },
      ].map((m) => (
        <g key={m.n}>
          <path d={`M${m.x} ${m.y - 30} a12 12 0 0 1 12 12 c0 9 -12 20 -12 20 s-12 -11 -12 -20 a12 12 0 0 1 12 -12z`} fill={m.c} />
          <circle cx={m.x} cy={m.y - 18} r="7" fill={WHITE} />
          <text x={m.x} y={m.y - 14} textAnchor="middle" fontSize="10" fontWeight="700" fill={m.c} fontFamily="sans-serif">
            {m.n}
          </text>
        </g>
      ))}
      <line x1="220" y1="50" x2="220" y2="20" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M220 20 h16 l-5 6 l5 6 h-16z" fill={AMBER} />
    </Svg>
  );
}

// ---------------------------------------------------------------- empty states
export function EmptyBoxArt(props: Props) {
  return (
    <Svg title="An empty box" {...props}>
      <path d="M60 70 l60 -22 l60 22 v56 l-60 22 l-60 -22z" fill={PALE} />
      <path d="M60 70 l60 22 l60 -22" fill="none" stroke={LIGHT} strokeWidth="3" strokeLinejoin="round" />
      <path d="M120 92 v56" stroke={LIGHT} strokeWidth="3" />
      <path d="M60 70 l-14 18 l60 22 l14 -18z" fill={LIGHT} />
      <path d="M180 70 l14 18 l-60 22 l-14 -18z" fill={BLUE} />
      <circle cx="120" cy="34" r="3" fill={AMBER} />
      <circle cx="140" cy="24" r="2" fill={AMBER} />
      <circle cx="100" cy="26" r="2" fill={AMBER} />
    </Svg>
  );
}

export function EmptyChipArt(props: Props) {
  return (
    <Svg title="An empty processor chip" {...props}>
      <rect x="76" y="40" width="88" height="88" rx="12" fill={PALE} stroke={LIGHT} strokeWidth="3" />
      <rect x="98" y="62" width="44" height="44" rx="8" fill={WHITE} stroke={BLUE} strokeWidth="3" strokeDasharray="6 4" />
      {[88, 104, 120, 136, 152].map((x) => (
        <g key={x}>
          <rect x={x - 3} y="28" width="6" height="12" rx="2" fill={LIGHT} />
          <rect x={x - 3} y="128" width="6" height="12" rx="2" fill={LIGHT} />
        </g>
      ))}
      {[52, 68, 84, 100, 116].map((y) => (
        <g key={y}>
          <rect x="64" y={y - 3} width="12" height="6" rx="2" fill={LIGHT} />
          <rect x="164" y={y - 3} width="12" height="6" rx="2" fill={LIGHT} />
        </g>
      ))}
      <text x="120" y="92" textAnchor="middle" fontSize="22" fontWeight="700" fill={BLUE} fontFamily="sans-serif">
        ?
      </text>
    </Svg>
  );
}

export function EmptyClipboardArt(props: Props) {
  return (
    <Svg title="An empty clipboard" {...props}>
      <rect x="78" y="34" width="84" height="104" rx="10" fill={PALE} stroke={LIGHT} strokeWidth="3" />
      <rect x="104" y="26" width="32" height="16" rx="5" fill={BLUE} />
      {[64, 82, 100].map((y, i) => (
        <rect key={y} x="94" y={y} width={i === 1 ? 40 : 52} height="6" rx="3" fill={LIGHT} strokeDasharray="4 3" />
      ))}
      <circle cx="152" cy="126" r="14" fill={AMBER} />
      <path d="M146 126 l4 4 l8 -9" fill="none" stroke={WHITE} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function EmptyChartArt(props: Props) {
  return (
    <Svg title="An empty chart" {...props}>
      <rect x="40" y="30" width="160" height="104" rx="10" fill={PALE} />
      <path d="M60 110 h120 M60 110 v-70" stroke={LIGHT} strokeWidth="3" strokeLinecap="round" />
      {[80, 104, 128, 152].map((x, i) => (
        <rect key={x} x={x} y={110 - [20, 40, 28, 52][i]} width="14" height={[20, 40, 28, 52][i]} rx="3" fill={WHITE} stroke={BLUE} strokeWidth="2" strokeDasharray="4 3" />
      ))}
      <circle cx="188" cy="44" r="4" fill={AMBER} />
    </Svg>
  );
}

/** One pin on a map with the comparison slots around it left blank. */
export function SinglePinArt(props: Props) {
  return (
    <Svg title="A single location pin with no other locations to compare" {...props}>
      <path d="M40 52 l52 -16 l56 16 l52 -16 v84 l-52 16 l-56 -16 l-52 16z" fill={PALE} />
      <path d="M92 36 v84 M148 52 v84" stroke={LIGHT} strokeWidth="2" />
      {[
        [62, 102],
        [176, 92],
        [196, 58],
      ].map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="8" fill={WHITE} stroke={LIGHT} strokeWidth="2" strokeDasharray="4 3" />
      ))}
      <path d="M120 40 a18 18 0 0 1 18 18 c0 14 -18 32 -18 32 s-18 -18 -18 -32 a18 18 0 0 1 18 -18z" fill={NAVY} />
      <circle cx="120" cy="58" r="7" fill={WHITE} />
      <ellipse cx="120" cy="96" rx="12" ry="3.5" fill={LIGHT} />
      <circle cx="146" cy="34" r="4" fill={AMBER} />
    </Svg>
  );
}

export function EmptyState({ art, children, className = "" }: { art: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`empty with-art ${className}`}>
      <div className="empty-art">{art}</div>
      <div>{children}</div>
    </div>
  );
}

/** Two chat bubbles with a sparkle: the assistant is ready to talk. */
export function ChatEmptyArt(props: Props) {
  return (
    <Svg title="Two speech bubbles ready for a conversation" {...props}>
      <circle cx="120" cy="82" r="62" fill={PALE} />
      <path d="M58 54 h88 a12 12 0 0 1 12 12 v34 a12 12 0 0 1 -12 12 h-54 l-20 16 v-16 h-14 a12 12 0 0 1 -12 -12 v-34 a12 12 0 0 1 12 -12z" fill={WHITE} stroke={LIGHT} strokeWidth="3" />
      <rect x="62" y="70" width="60" height="6" rx="3" fill={LIGHT} />
      <rect x="62" y="84" width="76" height="6" rx="3" fill={LIGHT} />
      <rect x="62" y="98" width="40" height="6" rx="3" fill={LIGHT} />
      <path d="M116 22 h68 a10 10 0 0 1 10 10 v26 a10 10 0 0 1 -10 10 h-8 v14 l-18 -14 h-42 a10 10 0 0 1 -10 -10 v-26 a10 10 0 0 1 10 -10z" fill={NAVY} />
      <rect x="128" y="36" width="44" height="5" rx="2.5" fill={WHITE} opacity="0.9" />
      <rect x="128" y="48" width="30" height="5" rx="2.5" fill={WHITE} opacity="0.6" />
      <path d="M200 96 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" fill={AMBER} />
      <path d="M38 118 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" fill={AMBER} />
      <Person x="44" y="40" s={0.8} color={BLUE} />
    </Svg>
  );
}

/** A plug meeting a socket under a cloud: connect the gateway. */
export function ConnectArt(props: Props) {
  return (
    <Svg title="A plug about to connect to a cloud gateway" {...props}>
      <circle cx="120" cy="84" r="60" fill={PALE} />
      <path d="M92 52 a18 18 0 0 1 34 -8 a14 14 0 0 1 26 8 a12 12 0 0 1 -2 24 h-58 a12 12 0 0 1 0 -24z" fill={WHITE} stroke={LIGHT} strokeWidth="3" />
      <rect x="40" y="96" width="46" height="22" rx="6" fill={NAVY} />
      <rect x="86" y="101" width="10" height="12" rx="2" fill={NAVY} />
      <rect x="96" y="103" width="8" height="3" fill={BLUE} />
      <rect x="96" y="109" width="8" height="3" fill={BLUE} />
      <rect x="128" y="94" width="34" height="26" rx="6" fill={WHITE} stroke={NAVY} strokeWidth="3" />
      <rect x="138" y="102" width="4" height="10" rx="1" fill={NAVY} />
      <rect x="148" y="102" width="4" height="10" rx="1" fill={NAVY} />
      <path d="M162 107 h26" stroke={NAVY} strokeWidth="3" strokeLinecap="round" />
      <path d="M188 107 v-34 h-28" stroke={LIGHT} strokeWidth="3" strokeLinecap="round" strokeDasharray="2 6" fill="none" />
      <circle cx="112" cy="107" r="5" fill={AMBER} />
      <path d="M58 60 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" fill={AMBER} />
    </Svg>
  );
}

/** A stack of conversation cards with a plus. */
export function ConversationsArt(props: Props) {
  return (
    <Svg title="A stack of conversation cards" {...props}>
      <circle cx="120" cy="82" r="58" fill={PALE} />
      <rect x="70" y="92" width="100" height="34" rx="8" fill={WHITE} stroke={LIGHT} strokeWidth="3" />
      <rect x="78" y="66" width="100" height="34" rx="8" fill={WHITE} stroke={LIGHT} strokeWidth="3" />
      <rect x="86" y="40" width="100" height="34" rx="8" fill={NAVY} />
      <circle cx="102" cy="57" r="7" fill={WHITE} opacity="0.9" />
      <rect x="116" y="50" width="52" height="5" rx="2.5" fill={WHITE} opacity="0.9" />
      <rect x="116" y="60" width="36" height="5" rx="2.5" fill={WHITE} opacity="0.6" />
      <circle cx="94" cy="83" r="6" fill={LIGHT} />
      <rect x="108" y="78" width="48" height="5" rx="2.5" fill={LIGHT} />
      <rect x="108" y="88" width="30" height="4" rx="2" fill={PALE} />
      <circle cx="186" cy="118" r="14" fill={AMBER} />
      <path d="M186 110 v16 M178 118 h16" stroke={WHITE} strokeWidth="3.5" strokeLinecap="round" />
    </Svg>
  );
}

/** Three agents linked to a front door: the assistant team. */
export function TeamArt(props: Props) {
  return (
    <Svg title="A front-door agent connected to specialist agents" {...props}>
      <circle cx="120" cy="82" r="58" fill={PALE} />
      <path d="M120 60 L70 110 M120 60 L120 112 M120 60 L170 110" stroke={LIGHT} strokeWidth="3" strokeDasharray="2 6" strokeLinecap="round" />
      <circle cx="120" cy="50" r="20" fill={NAVY} />
      <Person x="120" y="54" s={0.9} color={WHITE} />
      <circle cx="70" cy="116" r="16" fill={WHITE} stroke={BLUE} strokeWidth="3" />
      <Person x="70" y="120" s={0.7} color={BLUE} />
      <circle cx="120" cy="118" r="16" fill={WHITE} stroke={BLUE} strokeWidth="3" />
      <Person x="120" y="122" s={0.7} color={BLUE} />
      <circle cx="170" cy="116" r="16" fill={WHITE} stroke={BLUE} strokeWidth="3" />
      <Person x="170" y="120" s={0.7} color={BLUE} />
      <path d="M188 46 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2z" fill={AMBER} />
    </Svg>
  );
}

/** Warehouse shelving with a gap and a shield: the hero. */
export function WarehouseArt(props: Props) {
  const box = (x: number, y: number, w: number, h: number, c: string) => <rect x={x} y={y} width={w} height={h} rx="2" fill={c} />;
  return (
    <Svg title="Warehouse shelves with one gap watched by a shield" {...props}>
      <circle cx="132" cy="80" r="70" fill={PALE} />
      <rect x="44" y="40" width="150" height="6" rx="2" fill={NAVY} />
      <rect x="44" y="82" width="150" height="6" rx="2" fill={NAVY} />
      <rect x="44" y="124" width="150" height="6" rx="2" fill={NAVY} />
      <rect x="44" y="40" width="5" height="96" fill={NAVY} />
      <rect x="189" y="40" width="5" height="96" fill={NAVY} />
      {box(54, 20, 22, 20, LIGHT)}
      {box(80, 26, 18, 14, BLUE)}
      {box(102, 18, 26, 22, LIGHT)}
      {box(132, 24, 20, 16, BLUE)}
      {box(156, 20, 26, 20, LIGHT)}
      {box(54, 62, 26, 20, BLUE)}
      <rect x="86" y="62" width="26" height="20" rx="2" fill="none" stroke={RED} strokeWidth="2.5" strokeDasharray="4 3" />
      {box(118, 64, 20, 18, LIGHT)}
      {box(142, 60, 24, 22, BLUE)}
      {box(170, 66, 14, 16, LIGHT)}
      {box(56, 106, 20, 18, LIGHT)}
      {box(80, 102, 28, 22, BLUE)}
      {box(112, 108, 22, 16, LIGHT)}
      {box(138, 104, 18, 20, BLUE)}
      {box(160, 106, 24, 18, LIGHT)}
      <path d="M206 54 l20 8 v14 c0 14 -9 24 -20 28 c-11 -4 -20 -14 -20 -28 v-14z" fill={NAVY} />
      <path d="M198 80 l6 6 l12 -13" fill="none" stroke={WHITE} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="99" cy="72" r="4" fill={AMBER} />
    </Svg>
  );
}

/** A flat line with one spike, flagged. */
export function SpikeArt(props: Props) {
  return (
    <Svg title="A steady line with one day that spikes and is flagged" {...props}>
      <rect x="24" y="24" width="192" height="112" rx="12" fill={PALE} />
      <path d="M36 110 h20 l10 -4 l10 6 l10 -3 l10 2 l10 -3 l8 1 l6 -62 l6 62 l10 -2 l10 3 l10 -2 l10 4 l10 -3 l10 2 h20" fill="none" stroke={BLUE} strokeWidth="3" strokeLinejoin="round" />
      <rect x="120" y="36" width="20" height="84" rx="4" fill={RED} opacity="0.14" />
      <circle cx="130" cy="48" r="7" fill={RED} />
      <path d="M130 44 v5 M130 52 v0.5" stroke={WHITE} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M36 128 h168" stroke={LIGHT} strokeWidth="2" />
      <text x="146" y="44" fontSize="10" fontFamily="sans-serif" fill={INK}>unusual</text>
    </Svg>
  );
}

/** A grid of tiles with a hot corner. */
export function HeatmapArt(props: Props) {
  const shades = [PALE, LIGHT, BLUE, NAVY];
  const grid = [
    [0, 0, 1, 0, 0, 1],
    [0, 1, 1, 0, 0, 0],
    [1, 1, 2, 1, 0, 0],
    [0, 2, 3, 2, 1, 0],
  ];
  return (
    <Svg title="A store by category grid with one hot spot" {...props}>
      <circle cx="120" cy="80" r="66" fill={PALE} />
      {grid.map((row, r) =>
        row.map((v, c) => <rect key={`${r}-${c}`} x={54 + c * 22} y={34 + r * 22} width="19" height="19" rx="3" fill={v === 3 ? RED : shades[v]} />),
      )}
      <circle cx="129" cy="106" r="15" fill="none" stroke={AMBER} strokeWidth="3" />
    </Svg>
  );
}

/** A clipboard work list, a clock and a magnifier. */
export function InvestigationArt(props: Props) {
  return (
    <Svg title="A prioritised work list with a clock and a magnifying glass" {...props}>
      <circle cx="116" cy="80" r="66" fill={PALE} />
      <rect x="62" y="26" width="84" height="112" rx="8" fill={WHITE} stroke={LIGHT} strokeWidth="3" />
      <rect x="88" y="20" width="32" height="12" rx="4" fill={NAVY} />
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <circle cx="78" cy={52 + i * 22} r="6" fill={i === 0 ? RED : i === 1 ? AMBER : LIGHT} />
          <rect x="90" y={48 + i * 22} width={i === 0 ? 44 : 36 - i * 4} height="7" rx="3.5" fill={i < 2 ? BLUE : LIGHT} />
        </g>
      ))}
      <circle cx="176" cy="54" r="22" fill={WHITE} stroke={NAVY} strokeWidth="4" />
      <path d="M176 42 v12 l8 6" stroke={NAVY} strokeWidth="3.5" strokeLinecap="round" fill="none" />
      <circle cx="168" cy="112" r="15" fill="none" stroke={NAVY} strokeWidth="5" />
      <line x1="179" y1="123" x2="194" y2="138" stroke={NAVY} strokeWidth="7" strokeLinecap="round" />
    </Svg>
  );
}

/** A magnifier over a small line chart with a gap between two lines. */
export function DrilldownArt(props: Props) {
  return (
    <Svg title="A magnifying glass over expected and counted stock lines that drift apart" {...props}>
      <circle cx="120" cy="80" r="64" fill={PALE} />
      <path d="M44 66 h30 v14 h28 v10 h30 v12 h32" fill="none" stroke={NAVY} strokeWidth="3.5" />
      <path d="M44 70 h30 v16 h28 v22 h30 v20 h32" fill="none" stroke={BLUE} strokeWidth="3.5" strokeDasharray="6 4" />
      <rect x="102" y="88" width="30" height="40" fill={RED} opacity="0.15" />
      <circle cx="160" cy="62" r="26" fill="none" stroke={NAVY} strokeWidth="6" />
      <line x1="179" y1="81" x2="204" y2="106" stroke={NAVY} strokeWidth="9" strokeLinecap="round" />
      <circle cx="160" cy="62" r="20" fill={WHITE} opacity="0.55" />
    </Svg>
  );
}

/** A bell with a small badge: no alerts yet. */
export function AlertBellArt(props: Props) {
  return (
    <Svg title="A quiet alert bell" {...props}>
      <circle cx="120" cy="80" r="60" fill={PALE} />
      <path d="M120 32 c-22 0 -34 16 -34 38 v20 l-12 16 h92 l-12 -16 v-20 c0 -22 -12 -38 -34 -38z" fill={NAVY} />
      <circle cx="120" cy="116" r="9" fill={BLUE} />
      <rect x="114" y="24" width="12" height="10" rx="5" fill={NAVY} />
      <circle cx="152" cy="42" r="11" fill={AMBER} />
      <path d="M40 60 q-8 20 0 40 M200 60 q8 20 0 40" stroke={LIGHT} strokeWidth="3" fill="none" strokeLinecap="round" />
    </Svg>
  );
}

/** Ticks and crosses on cards flowing back into a brain-like node: teams teach the model. */
export function FeedbackArt(props: Props) {
  return (
    <Svg title="Reviewed alerts with ticks and crosses flowing back to the model" {...props}>
      <circle cx="120" cy="80" r="64" fill={PALE} />
      {[0, 1, 2].map((i) => (
        <g key={i}>
          <rect x={38} y={34 + i * 34} width="70" height="24" rx="6" fill={WHITE} stroke={LIGHT} strokeWidth="2.5" />
          <rect x={48} y={43 + i * 34} width="34" height="6" rx="3" fill={LIGHT} />
          {i === 1 ? (
            <path d={`M90 ${41 + i * 34} l10 10 M100 ${41 + i * 34} l-10 10`} stroke={RED} strokeWidth="3" strokeLinecap="round" />
          ) : (
            <path d={`M88 ${46 + i * 34} l5 5 l9 -10`} stroke={GOOD} strokeWidth="3" fill="none" strokeLinecap="round" />
          )}
        </g>
      ))}
      <path d="M112 80 C 132 80 140 80 150 80" stroke={BLUE} strokeWidth="3" strokeDasharray="4 4" />
      <path d="M146 74 l8 6 l-8 6" fill="none" stroke={BLUE} strokeWidth="3" />
      <rect x="160" y="52" width="56" height="56" rx="14" fill={NAVY} />
      <circle cx="188" cy="80" r="14" fill="none" stroke={WHITE} strokeWidth="3" />
      <circle cx="188" cy="80" r="5" fill={AMBER} />
    </Svg>
  );
}
