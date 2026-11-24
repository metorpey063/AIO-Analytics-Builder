// Site map, drawn as an aerial view of the site: terrain, an open pit, waste dumps, the lots the places sit in,
// haul roads with the traffic on each road, the equipment, and a truck at each truck's latest place.
import { useState } from 'react';
import { numericCellValue } from '@analytics/data-app-sdk';
import { useQuery } from '@analytics/data-app-sdk/react';
import { ChartCard } from '@analytics/data-app-ui-kit/components/react/ChartCard';
import { QueryBoundary } from '@analytics/data-app-ui-kit/components/react/connected/QueryBoundary';
import { Skeleton } from '@analytics/data-app-ui-kit/components/react/Skeleton';
import { useContainerWidth } from '@analytics/data-app-ui-kit/charts/react/useContainerWidth';

type Pt = [number, number];
type Row = Record<string, unknown>;

interface TipField { field: string; label?: string; format?: string }   // format: percent, number, currency or a unit (min, L)
interface Layer { queryId: string; label?: string; x: string; y: string; tooltip?: TipField[] }
interface Routes {
  queryId: string; fromX: string; fromY: string; toX: string; toY: string; weight?: string; color?: string;
  fromLabel?: string; toLabel?: string; weightLabel?: string; colorLabel?: string; tooltip?: TipField[];
}
interface Trucks { queryId: string; id: string; x: string; y: string; date?: string; noun?: string }

export interface SiteMapProps {
  queryId: string;            // one row per place: label, x, y (0-100 grid), size and color measures, zone
  label: string;
  x: string;
  y: string;
  size?: string;
  color?: string;
  zone?: string;
  highlight?: string;         // a zone value to outline in red
  lowerIsBetter?: boolean;    // true (default): a higher color value is worse
  colorLabel?: string;
  format?: string;            // format of the color measure
  tooltip?: TipField[];       // extra fields of the main query shown when hovering a place
  markers?: Layer;            // fixed equipment (loaders)
  routes?: Routes;            // traffic between two places, drawn along the road network
  trucks?: Trucks;            // moving things; the latest row per id wins
  title?: string;
}

// Text of a cell (a scalar or a {value, display} pair)
function text(cell: unknown): string {
  if (cell && typeof cell === 'object' && 'value' in (cell as Record<string, unknown>)) {
    return String((cell as Record<string, unknown>).value ?? '');
  }
  return cell == null ? '' : String(cell);
}

function rowsOf(result: unknown): Row[] {
  const r = result as { rows?: Row[] } | undefined;
  return r && Array.isArray(r.rows) ? r.rows : [];
}

// A value for a tooltip: percent (0.62 -> 62.0%), number, currency, or a unit word (min, L)
function fmt(v: unknown, format?: string): string {
  const raw = text(v);
  if (raw !== '' && !/^\s*-?\d+(\.\d+)?(e-?\d+)?\s*$/i.test(raw)) return raw;   // text (a mineral, a name) stays text
  const n = numericCellValue(v);
  if (!Number.isFinite(n)) return '–';
  if (format === 'percent') return `${(n * 100).toFixed(1)}%`;
  const num = Math.abs(n) >= 1000 ? `${(n / 1000).toFixed(1)}K` : n.toFixed(Math.abs(n) < 10 ? 2 : Math.abs(n) >= 100 ? 0 : 1);
  if (format === 'currency') return `$${num}`;
  return format && format !== 'number' ? `${num} ${format}` : num;
}
const short = (l: string) => l.replace(/^avg\.?\s+/i, '').replace(/\s*\((min|l|tonnes|t)\)\s*$/i, '').toLowerCase();
const avgLabel = (l: string) => (/^avg/i.test(l) ? l : `Avg ${l}`);

interface Tip { x: number; y: number; key?: string; title: string; lines: [string, string][]; groups: [string, [string, string][]][] }

const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const pathD = (pts: Pt[]) => pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join('');

// Green for better, red for worse, from the theme's semantic colors
function shade(v: number, lo: number, hi: number, lowerIsBetter: boolean): string {
  const t = Math.max(0, Math.min(1, (v - lo) / Math.max(1e-9, hi - lo)));
  const bad = Math.round((lowerIsBetter ? t : 1 - t) * 100);
  return `color-mix(in srgb, var(--sem-danger) ${bad}%, var(--sem-success))`;
}

// The same site always draws the same way
function seeded(name: string) {
  let s = 0;
  for (const ch of name) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), s | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// A wobbly closed outline (a pit bench, a dump), smooth through jittered points
function blob(cx: number, cy: number, rx: number, ry: number, jit: number, phase: number): string {
  const n = 56, pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const th = (2 * Math.PI * i) / n;
    const f = 1 + jit * (Math.sin(3 * th + phase) * 0.5 + Math.sin(5 * th + phase * 1.7) * 0.3 + Math.sin(8 * th + phase * 2.3) * 0.2);
    pts.push([cx + rx * f * Math.cos(th), cy + ry * f * Math.sin(th)]);
  }
  const mid = (i: number): Pt => [(pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2];
  let d = `M${mid(0)[0].toFixed(1)},${mid(0)[1].toFixed(1)}`;
  for (let i = 1; i <= n; i++) {
    const c = pts[i % n], m = mid(i % n);
    d += ` Q${c[0].toFixed(1)},${c[1].toFixed(1)} ${m[0].toFixed(1)},${m[1].toFixed(1)}`;
  }
  return d + 'Z';
}

const HALO = { stroke: 'rgba(255,255,255,0.85)', strokeWidth: 3, paintOrder: 'stroke' as const, strokeLinejoin: 'round' as const };

export function SiteMap(props: SiteMapProps) {
  const main = useQuery(props.queryId);
  const markers = useQuery(props.markers?.queryId ?? props.queryId);
  const routes = useQuery(props.routes?.queryId ?? props.queryId);
  const trucks = useQuery(props.trucks?.queryId ?? props.queryId);
  return (
    <ChartCard title={props.title}>
      <QueryBoundary queryId={props.queryId} skeleton={<Skeleton variant="chart" height={460} />}>
        {() => (
          <MapBody
            {...props}
            places={rowsOf(main.result)}
            marks={props.markers ? rowsOf(markers.result) : []}
            links={props.routes ? rowsOf(routes.result) : []}
            movers={props.trucks ? rowsOf(trucks.result) : []}
          />
        )}
      </QueryBoundary>
    </ChartCard>
  );
}

function MapBody(p: SiteMapProps & { places: Row[]; marks: Row[]; links: Row[]; movers: Row[] }) {
  const { ref, width } = useContainerWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  if (!width) return <div ref={ref} style={{ width: '100%', minHeight: 460 }} />;
  const W = Math.max(460, Math.min(1100, width)), H = Math.round(W * 0.62), P = 28;
  const lowerIsBetter = p.lowerIsBetter !== false;
  const rnd = seeded(p.title ?? (p.places[0] ? text(p.places[0][p.label]) : 'site'));
  const uid = `aio${Math.floor(rnd() * 1e9)}`;
  const X = (v: unknown) => P + numericCellValue(v) / 100 * (W - 2 * P);
  const Y = (v: unknown) => H - P - numericCellValue(v) / 100 * (H - 2 * P);
  const key = p.color ?? p.size ?? '';
  const vals = p.places.map((r) => numericCellValue(r[key]));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const sizes = p.places.map((r) => numericCellValue(r[p.size ?? key]));
  const smin = Math.min(...sizes), smax = Math.max(...sizes);

  // Lots around the places in each zone; the gate is the edge facing the equipment
  const loaderPts: Pt[] = p.markers ? p.marks.map((m) => [X(m[p.markers!.x]), Y(m[p.markers!.y])]) : [];
  const ex = loaderPts.length ? loaderPts.reduce((t, q) => t + q[0], 0) / loaderPts.length : W / 2;
  const ey = loaderPts.length ? loaderPts.reduce((t, q) => t + q[1], 0) / loaderPts.length : H / 2;
  const lots: { z: string; x0: number; x1: number; y0: number; y1: number }[] = [];
  const gates: Record<string, Pt> = {};
  if (p.zone) {
    const groups: Record<string, Row[]> = {};
    p.places.forEach((r) => { (groups[text(r[p.zone!])] = groups[text(r[p.zone!])] || []).push(r); });
    Object.keys(groups).forEach((z) => {
      const xs = groups[z].map((r) => X(r[p.x])), ys = groups[z].map((r) => Y(r[p.y]));
      const L = { z, x0: Math.min(...xs) - 26, x1: Math.max(...xs) + 26, y0: Math.min(...ys) - 40, y1: Math.max(...ys) + 22 };
      lots.push(L);
      gates[z] = [Math.max(L.x0 + 14, Math.min(L.x1 - 14, ex)), ey > (L.y0 + L.y1) / 2 ? L.y1 : L.y0];
    });
  }
  // The pit between the loaders; lots and roads sit over its rim
  const clear = lots.reduce((m, L) => Math.min(m, Math.hypot(Math.max(L.x0 - ex, 0, ex - L.x1), Math.max(L.y0 - ey, 0, ey - L.y1))), 1e9);
  const spread = loaderPts.reduce((m, q) => Math.max(m, dist(q, [ex, ey])), 0);
  const pr = Math.max(40, Math.min(clear + 18, spread * 0.85));
  const hasPit = loaderPts.length >= 2;
  const pitR: Pt = [pr * 1.4, pr * 0.9];
  const phase = rnd() * 6;
  // Waste dumps in the open ground away from the lots, the loaders and the pit
  const cands: [number, Pt][] = [];
  for (let gx = 0.1; gx <= 0.9; gx += 0.1) {
    for (let gy = 0.12; gy <= 0.88; gy += 0.12) {
      const q: Pt = [W * gx, H * gy];
      let free = dist(q, [ex, ey]) - pr * 1.5;
      lots.forEach((L) => { free = Math.min(free, Math.hypot(Math.max(L.x0 - q[0], 0, q[0] - L.x1), Math.max(L.y0 - q[1], 0, q[1] - L.y1)) - 30); });
      loaderPts.forEach((lp) => { free = Math.min(free, dist(q, lp) - 40); });
      cands.push([free, q]);
    }
  }
  const dumps: [number, Pt][] = [];
  cands.sort((a, b) => b[0] - a[0]).forEach((c) => {
    if (dumps.length < 2 && c[0] >= 20 && dumps.every((d) => dist(d[1], c[1]) > Math.min(160, c[0] * 2.2))) dumps.push(c);
  });
  const dumpPhase = dumps.map(() => rnd() * 6);

  // Road network: gates and loaders joined to their two nearest neighbours plus a spanning tree, each road a curve
  // that swings round the pit rim rather than crossing the pit
  const net: Pt[] = Object.keys(gates).map((z) => gates[z]).concat(loaderPts);
  const edgeKey = (i: number, j: number) => (i < j ? `${i}-${j}` : `${j}-${i}`);
  const edges = new Set<string>();
  net.forEach((q, i) => {
    net.map((q2, j) => [j, dist(q, q2)] as [number, number]).filter((e) => e[0] !== i)
      .sort((a, b) => a[1] - b[1]).slice(0, 2).forEach((e) => edges.add(edgeKey(i, e[0])));
  });
  const inTree = [0], rest = net.map((_, i) => i).slice(1);
  while (rest.length) {
    let best: [number, number, number] | null = null;
    for (const i of inTree) for (const j of rest) { const d = dist(net[i], net[j]); if (!best || d < best[2]) best = [i, j, d]; }
    edges.add(edgeKey(best![0], best![1]));
    inTree.push(best![1]);
    rest.splice(rest.indexOf(best![1]), 1);
  }
  const geom: Record<string, Pt[]> = {};
  const adj: [number, number][][] = net.map(() => []);
  Array.from(edges).forEach((k, n) => {
    const [i, j] = k.split('-').map(Number), A = net[i], B = net[j], len = dist(A, B), side = n % 2 ? 1 : -1;
    let bx = (A[0] + B[0]) / 2 + side * (-(B[1] - A[1]) / Math.max(1e-9, len)) * len * 0.14;
    let by = (A[1] + B[1]) / 2 + side * ((B[0] - A[0]) / Math.max(1e-9, len)) * len * 0.14;
    if (hasPit) {
      const t0 = Math.max(0, Math.min(1, ((ex - A[0]) * (B[0] - A[0]) + (ey - A[1]) * (B[1] - A[1])) / Math.max(1e-9, len * len)));
      const px = A[0] + t0 * (B[0] - A[0]), py = A[1] + t0 * (B[1] - A[1]);
      if (Math.hypot((px - ex) / (pitR[0] * 1.1), (py - ey) / (pitR[1] * 1.1)) < 1) {
        let nx = px - ex, ny = py - ey, nl = Math.hypot(nx, ny);
        if (nl < 1) { nx = -(B[1] - A[1]); ny = B[0] - A[0]; nl = len; }
        bx = ex + (nx / nl) * pitR[0] * 2.3;
        by = ey + (ny / nl) * pitR[1] * 2.3;
      }
    }
    const pts: Pt[] = [];
    for (let s = 0; s <= 14; s++) {
      const t = s / 14;
      pts.push([(1 - t) ** 2 * A[0] + 2 * (1 - t) * t * bx + t * t * B[0], (1 - t) ** 2 * A[1] + 2 * (1 - t) * t * by + t * t * B[1]]);
    }
    geom[k] = pts;
    adj[i].push([j, len]);
    adj[j].push([i, len]);
  });
  const nearest = (q: Pt) => net.reduce((b, n2, i) => (dist(n2, q) < dist(net[b], q) ? i : b), 0);
  const shortest = (a: number, b: number): string[] => {
    const d = net.map(() => Infinity), prev = net.map(() => -1), done = new Set<number>();
    d[a] = 0;
    for (;;) {
      let u = -1;
      d.forEach((v, i) => { if (!done.has(i) && v < Infinity && (u < 0 || v < d[u])) u = i; });
      if (u < 0 || u === b) break;
      done.add(u);
      adj[u].forEach(([v, w]) => { if (d[u] + w < d[v]) { d[v] = d[u] + w; prev[v] = u; } });
    }
    const out: string[] = [];
    for (let v = b; prev[v] >= 0; v = prev[v]) out.unshift(edgeKey(prev[v], v));
    return out;
  };
  // Traffic per road: as thick as the cycles on it, shaded by their weighted average
  const traffic: Record<string, { pts: Pt[]; w: number; cw: number; n: number; routes: Row[] }> = {};
  const add = (k: string, pts: Pt[], w: number, c: number | null, route: Row) => {
    const t = (traffic[k] = traffic[k] || { pts, w: 0, cw: 0, n: 0, routes: [] });
    t.w += w;
    if (c !== null) { t.cw += w * c; t.n += w; }
    t.routes.push(route);
  };
  if (p.routes && net.length > 1) {
    const R = p.routes;
    p.links.forEach((r) => {
      const from: Pt = [X(r[R.fromX]), Y(r[R.fromY])], to: Pt = [X(r[R.toX]), Y(r[R.toY])];
      const w = R.weight ? numericCellValue(r[R.weight]) : 1, c = R.color ? numericCellValue(r[R.color]) : null;
      const place = p.places.find((pl) => Math.abs(X(pl[p.x]) - from[0]) < 0.5 && Math.abs(Y(pl[p.y]) - from[1]) < 0.5);
      const z = place && p.zone ? text(place[p.zone]) : '';
      const start = gates[z] ?? from;
      if (start !== from) add(`lane:${from}`, [from, start], w, c, r);
      shortest(nearest(start), nearest(to)).forEach((k) => add(k, geom[k], w, c, r));
    });
  }
  const tk = Object.keys(traffic);
  const wmax = Math.max(1e-9, ...tk.map((k) => traffic[k].w));
  const avg = (k: string) => (traffic[k].n ? traffic[k].cw / traffic[k].n : 0);
  const clo = Math.min(...tk.map(avg)), chi = Math.max(...tk.map(avg));
  tk.sort((a, b) => (lowerIsBetter ? avg(a) - avg(b) : avg(b) - avg(a)));
  const lanes = tk.filter((k) => k.startsWith('lane:'));

  // Trucks: the latest row per id, parked around the place they're at
  const latest: Record<string, Row> = {};
  if (p.trucks) {
    const T = p.trucks;
    p.movers.forEach((m) => {
      const id = text(m[T.id]), prev = latest[id];
      if (!prev || (T.date && text(m[T.date]) > text(prev[T.date]))) latest[id] = m;
    });
  }
  const crowd: Record<string, number> = {};
  const parked = Object.keys(latest).sort().map((id) => {
    const m = latest[id], T = p.trucks!;
    const at = `${text(m[T.x])},${text(m[T.y])}`, n = (crowd[at] = (crowd[at] || 0) + 1), a = n * 2.4, r = 12 + 4 * Math.floor(n / 6);
    return { id, x: X(m[T.x]) + Math.cos(a) * r, y: Y(m[T.y]) + Math.sin(a) * r, rot: ((n * 47) % 180) - 90 };
  });

  // Tooltips: a card that follows the pointer (or sits by the focused mark)
  const fields = (row: Row, list?: TipField[]): [string, string][] =>
    (list ?? []).filter((f) => row[f.field] != null).map((f) => [f.label ?? f.field, fmt(row[f.field], f.format)]);
  const R2 = p.routes;
  const routeName = (r: Row) => (R2 && (R2.fromLabel || R2.toLabel) ? `${text(r[R2.fromLabel ?? ''])} → ${text(r[R2.toLabel ?? ''])}` : 'Route');
  const roadTip = (k: string): Omit<Tip, 'x' | 'y'> => {
    const t = traffic[k], v = t.n ? t.cw / t.n : null;
    const lines: [string, string][] = [[`${R2?.weightLabel ?? 'Cycles'} on this road`, fmt(t.w)]];
    if (v !== null && R2?.color) lines.push([avgLabel(R2.colorLabel ?? R2.color), fmt(v, p.format)]);
    const shown = (R2?.tooltip ?? []).map((f) => f.field);
    const groups: [string, [string, string][]][] = t.routes
      .slice().sort((a, b) => numericCellValue(b[R2?.weight ?? '']) - numericCellValue(a[R2?.weight ?? ''])).slice(0, 4)
      .map((r) => {
        const ls = fields(r, R2?.tooltip);
        if (R2?.weight && !shown.includes(R2.weight)) ls.push([R2.weightLabel ?? 'Cycles', fmt(r[R2.weight])]);
        return [routeName(r), ls];
      });
    if (t.routes.length > 4) groups.push([`+ ${t.routes.length - 4} more routes on this road`, []]);
    return { key: k, title: k.startsWith('lane:') ? 'Lot lane' : 'Haul road', lines, groups };
  };
  const placeTip = (r: Row): Omit<Tip, 'x' | 'y'> => ({
    title: text(r[p.label]),
    lines: [...(p.zone ? [['Zone', text(r[p.zone])] as [string, string]] : []), [p.colorLabel ?? key, fmt(r[key], p.format)], ...fields(r, p.tooltip)],
    groups: [],
  });
  const markerTip = (m: Row): Omit<Tip, 'x' | 'y'> => ({ title: text(m[p.markers?.label ?? '']), lines: fields(m, p.markers?.tooltip), groups: [] });
  // Positions are read while the event is live (React clears currentTarget once the handler returns)
  const svgOf = (el: EventTarget | null): SVGSVGElement | null => {
    const node = el as SVGElement | null;
    return node ? (node.ownerSVGElement ?? (node instanceof SVGSVGElement ? node : null)) : null;
  };
  const at = (e: { clientX: number; clientY: number; currentTarget: EventTarget | null; target: EventTarget | null }) => {
    const box = svgOf(e.currentTarget ?? e.target)?.getBoundingClientRect();
    return { x: e.clientX - (box?.left ?? 0) + 14, y: e.clientY - (box?.top ?? 0) + 14 };
  };
  const near = (el: Element | null) => {
    if (!el) return { x: 20, y: 20 };
    const svgBox = svgOf(el)?.getBoundingClientRect(), b = el.getBoundingClientRect();
    return { x: b.left - (svgBox?.left ?? 0) + b.width / 2 + 10, y: b.top - (svgBox?.top ?? 0) + b.height / 2 + 10 };
  };
  const tipProps = (label: string, build: () => Omit<Tip, 'x' | 'y'>) => ({
    role: 'button' as const, tabIndex: 0, 'aria-label': label, style: { cursor: 'pointer', outline: 'none' },
    onMouseEnter: (e: React.MouseEvent<SVGElement>) => { const pos = at(e); setTip({ ...build(), ...pos }); },
    onMouseMove: (e: React.MouseEvent<SVGElement>) => { const pos = at(e); setTip((t) => (t ? { ...t, ...pos } : t)); },
    onMouseLeave: () => setTip(null),
    onFocus: (e: React.FocusEvent<SVGElement>) => { const pos = near(e.currentTarget); setTip({ ...build(), ...pos }); },
    onBlur: () => setTip(null),
  });

  const describe = `Aerial site map of ${p.places.length} places, ${p.marks.length} loaders and ${parked.length} ` +
    `${p.trucks?.noun ?? 'trucks'}; ${p.colorLabel ?? key} from ${lo.toFixed(1)} to ${hi.toFixed(1)}.`;
  const seedA = Math.floor(rnd() * 99), seedB = Math.floor(rnd() * 99), seedC = Math.floor(rnd() * 99);
  return (
    <div ref={ref} style={{ width: '100%', position: 'relative' }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={describe} style={{ maxWidth: '100%', display: 'block' }}>
        <defs>
          <filter id={`${uid}g`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.006" numOctaves={5} seed={seedA} result="h" />
            <feDiffuseLighting in="h" surfaceScale={16} lightingColor="rgb(255,244,226)" result="lit">
              <feDistantLight azimuth={235} elevation={38} />
            </feDiffuseLighting>
            <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves={4} seed={seedB} result="c" />
            <feColorMatrix in="c" type="matrix" values="0.30 0 0 0 0.50  0.26 0 0 0 0.41  0.18 0 0 0 0.29  0 0 0 0 1" result="soil" />
            <feBlend in="soil" in2="lit" mode="multiply" result="ground" />
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={1} seed={5} result="grain" />
            <feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.12 0" result="grainA" />
            <feComposite in="grainA" in2="ground" operator="over" />
          </filter>
          <filter id={`${uid}v`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves={4} seed={seedC} />
            <feColorMatrix type="matrix" values="0 0 0 0 0.26  0 0 0 0 0.31  0 0 0 0 0.17  0 0 0 -14 5.9" />
          </filter>
          <filter id={`${uid}r`} x="0" y="0" width="100%" height="100%">
            <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves={2} seed={9} />
            <feColorMatrix type="matrix" values="0 0 0 0 0.62  0 0 0 0 0.58  0 0 0 0 0.52  0 0 0 0.35 0" />
          </filter>
          <clipPath id={`${uid}c`}><rect x={4} y={4} width={W - 8} height={H - 8} rx={10} /></clipPath>
        </defs>
        <g clipPath={`url(#${uid}c)`}>
          <rect x={0} y={0} width={W} height={H} fill="rgb(160,141,108)" />
          <rect x={0} y={0} width={W} height={H} filter={`url(#${uid}g)`} />
          <rect x={0} y={0} width={W} height={H} filter={`url(#${uid}v)`} opacity={0.6} />
          {hasPit && Array.from({ length: 8 }, (_, bn) => {
            const f = 1 - bn / 9, tone = bn / 8;
            const fill = `rgb(${Math.round(170 - 70 * tone)},${Math.round(152 - 62 * tone)},${Math.round(126 - 46 * tone)})`;
            return (
              <g key={`bench-${bn}`}>
                <path d={blob(ex + bn * 1.6, ey + bn * 1.1, pr * f * 1.4, pr * f * 0.9, 0.09, phase)} fill={fill}
                      stroke="rgba(240,228,205,0.55)" strokeWidth={1.6} />
                <path d={blob(ex + bn * 1.6 + 1.5, ey + bn * 1.1 + 2, pr * f * 1.4 - 3, pr * f * 0.9 - 3, 0.09, phase)} fill="none"
                      stroke="rgba(40,30,20,0.25)" strokeWidth={2} />
              </g>
            );
          })}
          {hasPit && (
            <path d={blob(ex + 13, ey + 9, pr * 0.18, pr * 0.11, 0.2, phase + 1)} fill="rgb(63,111,115)"
                  stroke="rgb(46,84,88)" strokeWidth={1} opacity={0.9} />
          )}
          {dumps.map((c, i) => (
            <g key={`dump-${i}`}>
              {[0, 1, 2, 3].map((lv) => {
                const dr = Math.min(70, c[0] * 0.8), k2 = 1 - lv * 0.2, c0 = 178 + lv * 10;
                return (
                  <path key={lv} d={blob(c[1][0], c[1][1] - lv * 2, dr * k2 * 1.3, dr * k2 * 0.8, 0.12, dumpPhase[i])}
                        fill={`rgb(${c0},${c0 - 8},${c0 - 22})`} stroke="rgba(60,50,40,0.25)" strokeWidth={1.2} />
                );
              })}
              <text x={c[1][0] - 24} y={c[1][1] + 4} fontSize={11} fontWeight={500} fill="rgb(87,96,106)" {...HALO}>
                {`Waste Dump ${i + 1}`}
              </text>
            </g>
          ))}
          {lots.map((L) => {
            const hot = p.highlight === L.z, w2 = L.x1 - L.x0, h2 = L.y1 - L.y0, roofX = L.x1 + 10;
            const bays: number[] = [];
            for (let bx = L.x0 + 10; bx < L.x1 - 6; bx += 14) bays.push(bx);
            return (
              <g key={`lot-${L.z}`}>
                <rect x={L.x0 - 3} y={L.y0 - 3} width={w2 + 6} height={h2 + 6} rx={6} fill="rgba(90,75,55,0.35)" />
                <rect x={L.x0} y={L.y0} width={w2} height={h2} rx={5} fill="rgb(185,176,160)" />
                <rect x={L.x0} y={L.y0} width={w2} height={h2} rx={5} filter={`url(#${uid}r)`} />
                {bays.map((bx) => (
                  <line key={bx} x1={bx} y1={L.y0 + 16} x2={bx} y2={L.y1 - 6} stroke="rgba(255,255,255,0.45)" strokeWidth={1} />
                ))}
                {roofX + 26 < W - 8 && (
                  <g>
                    <rect x={roofX + 3} y={L.y0 + 7} width={24} height={16} fill="rgba(0,0,0,0.3)" />
                    <rect x={roofX} y={L.y0 + 4} width={24} height={16} fill="rgb(223,227,230)" stroke="rgb(154,164,174)" strokeWidth={0.8} />
                    <rect x={roofX + 3} y={L.y0 + 26} width={16} height={11} fill="rgba(0,0,0,0.3)" />
                    <rect x={roofX} y={L.y0 + 23} width={16} height={11} fill="rgb(201,205,209)" stroke="rgb(154,164,174)" strokeWidth={0.8} />
                  </g>
                )}
                {hot && (
                  <rect x={L.x0 - 6} y={L.y0 - 6} width={w2 + 12} height={h2 + 12} rx={8} fill="rgba(207,34,46,0.10)"
                        stroke="var(--sem-danger)" strokeWidth={2.5} strokeDasharray="7 4" />
                )}
                <text x={L.x0 + 2} y={L.y0 - 9} fontSize={12} fontWeight={700} fill={hot ? 'var(--sem-danger)' : 'rgb(31,35,40)'} {...HALO}>
                  {L.z}
                </text>
              </g>
            );
          })}
          {Object.keys(geom).map((k) => (
            <path key={`edge-${k}`} d={pathD(geom[k])} fill="none" stroke="rgba(80,65,45,0.45)" strokeWidth={16} strokeLinecap="round" />
          ))}
          {lanes.map((k) => (
            <path key={`lane-${k}`} d={pathD(traffic[k].pts)} fill="none" stroke="rgb(216,201,166)" strokeWidth={5} strokeLinecap="round" />
          ))}
          {Object.keys(geom).map((k) => (
            <g key={`road-${k}`}>
              <path d={pathD(geom[k])} fill="none" stroke="rgb(216,201,166)" strokeWidth={12} strokeLinecap="round" />
              <path d={pathD(geom[k])} fill="none" stroke="rgba(150,130,100,0.5)" strokeWidth={1} strokeDasharray="6 9" />
            </g>
          ))}
          {tk.map((k) => (
            <path key={`traffic-${k}`} d={pathD(traffic[k].pts)} fill="none" strokeLinecap="round" strokeLinejoin="round"
                  stroke={p.routes?.color ? shade(avg(k), clo, chi, lowerIsBetter) : 'var(--text-secondary)'}
                  strokeWidth={1.5 + (5 * traffic[k].w) / wmax} strokeOpacity={0.9} />
          ))}
        </g>
        {tk.map((k) => (
          <path key={`hit-${k}`} d={pathD(traffic[k].pts)} fill="none" strokeLinecap="round" strokeWidth={16}
                stroke={tip?.key === k ? 'rgba(255,255,255,0.35)' : 'transparent'}
                {...tipProps(`Road with ${fmt(traffic[k].w)} cycles`, () => roadTip(k))} />
        ))}
        {p.markers && p.marks.map((m) => {
          const mx = X(m[p.markers!.x]), my = Y(m[p.markers!.y]), name = text(m[p.markers!.label ?? p.markers!.x]);
          const rot = (Math.atan2(ey - my, ex - mx) * 180) / Math.PI;
          return (
            <g key={`loader-${name}`}>
              <g transform={`translate(${mx},${my}) rotate(${rot.toFixed(0)})`} {...tipProps(name, () => markerTip(m))}>
                <rect x={-8} y={-7} width={20} height={18} rx={2} fill="rgba(0,0,0,0.35)" />
                <rect x={-10} y={-9} width={20} height={4} fill="rgb(43,43,43)" />
                <rect x={-10} y={5} width={20} height={4} fill="rgb(43,43,43)" />
                <rect x={-8} y={-6} width={14} height={12} rx={2} fill="rgb(242,183,5)" stroke="rgb(107,82,0)" strokeWidth={0.8} />
                <rect x={4} y={-2} width={16} height={4} fill="rgb(217,158,0)" />
                <rect x={19} y={-4} width={5} height={8} rx={1} fill="rgb(58,58,58)" />
              </g>
              <text x={mx + 14} y={my - 10} fontSize={11} fontWeight={600} fill="rgb(31,35,40)" pointerEvents="none" {...HALO}>{name}</text>
            </g>
          );
        })}
        {p.places.map((r) => {
          const v = numericCellValue(r[key]), name = text(r[p.label]);
          const rad = Math.max(6, 0.75 * (7 + (11 * (numericCellValue(r[p.size ?? key]) - smin)) / Math.max(1e-9, smax - smin)));
          const c = shade(v, lo, hi, lowerIsBetter);
          return (
            <g key={`place-${name}`}>
              <circle cx={X(r[p.x])} cy={Y(r[p.y])} r={rad} fill={c} fillOpacity={0.55} stroke={c} strokeWidth={2.5}
                      {...tipProps(`${name}: ${fmt(v, p.format)}`, () => placeTip(r))} />
              <text x={X(r[p.x])} y={Y(r[p.y]) - rad - 4} textAnchor="middle" fontSize={10} fontWeight={500} fill="rgb(31,35,40)"
                    pointerEvents="none" {...HALO}>
                {name}
              </text>
            </g>
          );
        })}
        {parked.map((t) => (
          <g key={`truck-${t.id}`} transform={`translate(${t.x.toFixed(1)},${t.y.toFixed(1)}) rotate(${t.rot})`}>
            <rect x={-4.5} y={-2.5} width={11} height={8} rx={1} fill="rgba(0,0,0,0.35)" />
            <rect x={-6} y={-4} width={10} height={8} rx={1} fill="rgb(245,196,0)" stroke="rgb(122,96,0)" strokeWidth={0.6} />
            <rect x={4} y={-3.5} width={3.5} height={7} rx={0.8} fill="rgb(58,58,58)" />
            <title>{t.id}</title>
          </g>
        ))}
      </svg>
      {tip && (
        <div role="tooltip" style={{ position: 'absolute', left: Math.min(tip.x, W - 330), top: Math.min(tip.y, H - 40), zIndex: 5,
                                     pointerEvents: 'none', minWidth: 220, maxWidth: 340, padding: '8px 10px', fontSize: 12,
                                     background: 'var(--surface-card)', color: 'var(--text-primary)', borderRadius: 8,
                                     border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-card-hover)' }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{tip.title}</div>
          {tip.lines.map(([l, v]) => (
            <div key={l} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--text-secondary)' }}>
              <span>{l}</span><b style={{ color: 'var(--text-primary)' }}>{v}</b>
            </div>
          ))}
          {tip.groups.map(([name, ls]) => (
            <div key={name} style={{ marginTop: 6, paddingTop: 5, borderTop: '1px solid var(--border-default)' }}>
              <div style={{ fontWeight: 600 }}>{name}</div>
              {ls.length > 0 && (
                <div style={{ color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                  {ls.map(([l, v], i) => (
                    <span key={l}>{i ? ' · ' : ''}{`${short(l)} `}<b style={{ color: 'var(--text-primary)' }}>{v}</b></span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        {`Rings: ${p.colorLabel ?? key}, green better, red worse. Yellow machines: loaders. Roads: thicker = more traffic`}
        {p.routes?.color ? ', shaded by the same measure' : ''}
        {parked.length ? `. ${parked.length} trucks: where each ${p.trucks?.noun ?? 'truck'} was last.` : '.'}
      </p>
    </div>
  );
}
