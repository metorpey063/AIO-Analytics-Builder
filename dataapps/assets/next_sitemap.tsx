// Site map: places on the site (e.g. parking spots) shaded by a measure, the lots they sit in, fixed equipment,
// the haul roads between them with the traffic on each road, and a dot per truck at its latest place.
import { numericCellValue } from '@analytics/data-app-sdk';
import { useQuery } from '@analytics/data-app-sdk/react';
import { ChartCard } from '@analytics/data-app-ui-kit/components/react/ChartCard';
import { QueryBoundary } from '@analytics/data-app-ui-kit/components/react/connected/QueryBoundary';
import { Skeleton } from '@analytics/data-app-ui-kit/components/react/Skeleton';
import { useContainerWidth } from '@analytics/data-app-ui-kit/charts/react/useContainerWidth';

type Pt = [number, number];
type Row = Record<string, unknown>;

interface Layer { queryId: string; label?: string; x: string; y: string }
interface Routes { queryId: string; fromX: string; fromY: string; toX: string; toY: string; weight?: string; color?: string }
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
  markers?: Layer;            // fixed equipment
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

const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const pathD = (pts: Pt[]) => pts.map((q, i) => `${i ? 'L' : 'M'}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join('');

// Green for better, red for worse, mixed from the theme's semantic colors
function shade(v: number, lo: number, hi: number, lowerIsBetter: boolean): string {
  const t = Math.max(0, Math.min(1, (v - lo) / Math.max(1e-9, hi - lo)));
  const bad = Math.round((lowerIsBetter ? t : 1 - t) * 100);
  return `color-mix(in srgb, var(--sem-danger) ${bad}%, var(--sem-success))`;
}

export function SiteMap(props: SiteMapProps) {
  const main = useQuery(props.queryId);
  const markers = useQuery(props.markers?.queryId ?? props.queryId);
  const routes = useQuery(props.routes?.queryId ?? props.queryId);
  const trucks = useQuery(props.trucks?.queryId ?? props.queryId);
  return (
    <ChartCard title={props.title}>
      <QueryBoundary queryId={props.queryId} skeleton={<Skeleton variant="chart" height={420} />}>
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
  if (!width) return <div ref={ref} style={{ width: '100%', minHeight: 420 }} />;
  const W = Math.max(420, width), H = Math.round(W * 0.62), P = 28;
  const lowerIsBetter = p.lowerIsBetter !== false;
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
  // The pit between the loaders, kept clear of every lot
  const clear = lots.reduce((m, L) => Math.min(m, Math.hypot(Math.max(L.x0 - ex, 0, ex - L.x1), Math.max(L.y0 - ey, 0, ey - L.y1))), 1e9);
  const spread = loaderPts.reduce((m, q) => Math.max(m, dist(q, [ex, ey])), 0);
  const pr = Math.max(24, Math.min(clear - 12, spread * 0.6));

  // Road network: gates and loaders joined to their two nearest neighbours plus a spanning tree, each road a curve
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
    const bx = (A[0] + B[0]) / 2 + side * (-(B[1] - A[1]) / Math.max(1e-9, len)) * len * 0.14;
    const by = (A[1] + B[1]) / 2 + side * ((B[0] - A[0]) / Math.max(1e-9, len)) * len * 0.14;
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
  const traffic: Record<string, { pts: Pt[]; w: number; cw: number; n: number }> = {};
  const add = (k: string, pts: Pt[], w: number, c: number | null) => {
    const t = (traffic[k] = traffic[k] || { pts, w: 0, cw: 0, n: 0 });
    t.w += w;
    if (c !== null) { t.cw += w * c; t.n += w; }
  };
  if (p.routes && net.length > 1) {
    const R = p.routes;
    p.links.forEach((r) => {
      const from: Pt = [X(r[R.fromX]), Y(r[R.fromY])], to: Pt = [X(r[R.toX]), Y(r[R.toY])];
      const w = R.weight ? numericCellValue(r[R.weight]) : 1, c = R.color ? numericCellValue(r[R.color]) : null;
      const place = p.places.find((pl) => Math.abs(X(pl[p.x]) - from[0]) < 0.5 && Math.abs(Y(pl[p.y]) - from[1]) < 0.5);
      const z = place && p.zone ? text(place[p.zone]) : '';
      const start = gates[z] ?? from;
      if (start !== from) add(`lane:${from}`, [from, start], w, c);
      shortest(nearest(start), nearest(to)).forEach((k) => add(k, geom[k], w, c));
    });
  }
  const tk = Object.keys(traffic);
  const wmax = Math.max(1e-9, ...tk.map((k) => traffic[k].w));
  const avg = (k: string) => (traffic[k].n ? traffic[k].cw / traffic[k].n : 0);
  const clo = Math.min(...tk.map(avg)), chi = Math.max(...tk.map(avg));
  tk.sort((a, b) => (lowerIsBetter ? avg(a) - avg(b) : avg(b) - avg(a)));

  // Moving things: the latest row per id, spread around the place they're at
  const latest: Record<string, Row> = {};
  if (p.trucks) {
    const T = p.trucks;
    p.movers.forEach((m) => {
      const id = text(m[T.id]), prev = latest[id];
      if (!prev || (T.date && text(m[T.date]) > text(prev[T.date]))) latest[id] = m;
    });
  }
  const crowd: Record<string, number> = {};
  const dots = Object.keys(latest).sort().map((id) => {
    const m = latest[id], T = p.trucks!;
    const at = `${text(m[T.x])},${text(m[T.y])}`, n = (crowd[at] = (crowd[at] || 0) + 1), a = n * 2.4, r = 12 + 4 * Math.floor(n / 6);
    return { id, x: X(m[T.x]) + Math.cos(a) * r, y: Y(m[T.y]) + Math.sin(a) * r };
  });

  const describe = `Site map of ${p.places.length} places, ${p.marks.length} pieces of equipment and ${dots.length} ` +
    `${p.trucks?.noun ?? 'trucks'}; ${p.colorLabel ?? key} from ${lo.toFixed(1)} to ${hi.toFixed(1)}.`;
  return (
    <div ref={ref} style={{ width: '100%' }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={describe} style={{ maxWidth: '100%', display: 'block' }}>
        <rect x={4} y={4} width={W - 8} height={H - 8} rx={10} fill="var(--surface-muted)" stroke="var(--border-default)" />
        {loaderPts.length >= 2 && [5, 4, 3, 2, 1].map((b) => (
          <ellipse key={b} cx={ex} cy={ey} rx={pr * (b / 5) * 1.35} ry={pr * (b / 5) * 0.85}
                   fill={`color-mix(in srgb, var(--text-secondary) ${8 + (5 - b) * 9}%, var(--surface-muted))`}
                   stroke="var(--border-default)" />
        ))}
        {lots.map((L) => {
          const hot = p.highlight === L.z;
          return (
            <g key={L.z}>
              <rect x={L.x0} y={L.y0} width={L.x1 - L.x0} height={L.y1 - L.y0} rx={10} strokeDasharray="5 4"
                    fill={hot ? 'color-mix(in srgb, var(--sem-danger) 12%, var(--surface-card))' : 'var(--surface-card)'}
                    stroke={hot ? 'var(--sem-danger)' : 'var(--border-default)'} strokeWidth={hot ? 2 : 1} />
              <text x={L.x0 + 2} y={L.y0 - 6} fontSize={11} fontWeight={600} fill={hot ? 'var(--sem-danger)' : 'var(--text-secondary)'}>{L.z}</text>
            </g>
          );
        })}
        {Object.keys(geom).map((k) => (
          <path key={`road-${k}`} d={pathD(geom[k])} fill="none" stroke="var(--border-default)" strokeWidth={10} strokeLinecap="round" />
        ))}
        {tk.map((k) => (
          <path key={`traffic-${k}`} d={pathD(traffic[k].pts)} fill="none" strokeLinecap="round" strokeLinejoin="round"
                stroke={p.routes?.color ? shade(avg(k), clo, chi, lowerIsBetter) : 'var(--text-secondary)'}
                strokeWidth={1.5 + 6.5 * traffic[k].w / wmax} strokeOpacity={0.85} />
        ))}
        {p.markers && p.marks.map((m) => {
          const mx = X(m[p.markers!.x]), my = Y(m[p.markers!.y]), name = text(m[p.markers!.label ?? p.markers!.x]);
          return (
            <g key={`marker-${name}`}>
              <rect x={mx - 9} y={my - 9} width={18} height={18} rx={3} fill="var(--text-primary)" stroke="var(--surface-card)" strokeWidth={2} />
              <text x={mx + 13} y={my + 4} fontSize={11} fontWeight={600} fill="var(--text-primary)">{name}</text>
            </g>
          );
        })}
        {p.places.map((r) => {
          const v = numericCellValue(r[key]), name = text(r[p.label]);
          const rad = 7 + 11 * (numericCellValue(r[p.size ?? key]) - smin) / Math.max(1e-9, smax - smin);
          return (
            <g key={`place-${name}`}>
              <circle cx={X(r[p.x])} cy={Y(r[p.y])} r={rad} fill={shade(v, lo, hi, lowerIsBetter)} fillOpacity={0.9}
                      stroke="var(--surface-card)" strokeWidth={1.5}>
                <title>{`${name}: ${v.toFixed(1)}`}</title>
              </circle>
              <text x={X(r[p.x])} y={Y(r[p.y]) - rad - 3} textAnchor="middle" fontSize={11} fill="var(--text-secondary)">{name}</text>
            </g>
          );
        })}
        {dots.map((d) => (
          <circle key={`mover-${d.id}`} cx={d.x} cy={d.y} r={3.6} fill="var(--chart-brand)" stroke="var(--surface-card)" strokeWidth={1}>
            <title>{d.id}</title>
          </circle>
        ))}
      </svg>
      <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
        {`Circles: ${p.colorLabel ?? key}, green better, red worse. Squares: equipment. Roads: thicker = more traffic`}
        {p.routes?.color ? ', shaded by the same measure' : ''}
        {dots.length ? `. ${dots.length} dots: where each ${p.trucks?.noun ?? 'truck'} was last.` : '.'}
      </p>
    </div>
  );
}
