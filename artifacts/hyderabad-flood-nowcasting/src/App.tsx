import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, type UseQueryResult } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/toaster';
import { ErrorBoundary } from '@/components/error-boundary';
import { LeafletMap, type GeoFeature, type LayerVisibility, type RouteLine } from '@/components/leaflet-map';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Check,
  ChevronRight,
  Droplets,
  Info,
  Map,
  MapPin,
  Menu,
  Navigation,
  RefreshCw,
  Route as RouteIcon,
  Search,
  ShieldCheck,
  Waves,
  X,
} from 'lucide-react';
import {
  getGetDataStatusQueryKey,
  getGetForecastStatusQueryKey,
  getGetForecastSummaryQueryKey,
  getGetHealthQueryKey,
  getGetMapLayersQueryKey,
  getGetPreprocessingStatusQueryKey,
  getGetSafeRouteQueryKey,
  getGetSystemStatusQueryKey,
  useGetDataStatus,
  useGetForecastStatus,
  useGetForecastSummary,
  useGetHealth,
  useGetMapLayers,
  useGetPreprocessingStatus,
  useGetSafeRoute,
  useGetSystemStatus,
} from '@workspace/api-client-react';
import type { GetSafeRouteForecastMinutes, RouteSummary } from '@workspace/api-client-react';
import { Route, Router as WouterRouter, Switch, useLocation } from 'wouter';
import NotFound from '@/pages/not-found';
import { searchHyderabadPlaces, type PlaceSearchResult } from '@/lib/geocoding';

const queryClient = new QueryClient();
type Horizon = GetSafeRouteForecastMinutes;
const horizons: Horizon[] = [0, 30, 60, 90, 120, 150, 180];

const layerLabels: Array<{ key: keyof LayerVisibility; label: string; color: string }> = [
  { key: 'flood', label: 'Flood depth + risk', color: '#cf5d50' },
  { key: 'roads', label: 'Road flood risk', color: '#e5944f' },
  { key: 'nalas', label: 'Nalas / drainage', color: '#2c8e8b' },
  { key: 'waterbodies', label: 'Water bodies', color: '#78c3be' },
  { key: 'boundary', label: 'GHMC boundary', color: '#176f76' },
];

function formatNumber(value: unknown, digits = 1) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function formatDistance(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${(value / 1000).toFixed(1)} km`
    : '—';
}

function riskLabel(value: number) {
  return value >= 4 ? 'Severe' : value === 3 ? 'High' : value === 2 ? 'Moderate' : value === 1 ? 'Low' : 'Very low';
}

function riskTone(value: number) {
  return value >= 4 ? 'red' : value >= 2 ? 'amber' : 'teal';
}

type FloodOutlook = {
  label: 'LOW FLOOD RISK' | 'MONITOR CONDITIONS' | 'ELEVATED FLOOD RISK' | 'HIGH FLOOD RISK';
  tone: 'teal' | 'amber' | 'red';
  guidance: string;
};

function deriveFloodOutlook(statistics?: {
  maximum_depth_cm?: number | null;
  risk_class_counts?: Record<string, number>;
}): FloodOutlook {
  const depth = Number(statistics?.maximum_depth_cm);
  const maxRiskClass = Math.max(
    0,
    ...Object.entries(statistics?.risk_class_counts ?? {})
      .filter(([, count]) => Number(count) > 0)
      .map(([risk]) => Number(risk))
      .filter(Number.isFinite),
  );
  const safeDepth = Number.isFinite(depth) ? depth : 0;

  if (maxRiskClass >= 3 || safeDepth >= 15) {
    return {
      label: 'HIGH FLOOD RISK',
      tone: 'red',
      guidance: 'Avoid water-affected corridors where possible. Use route screening as a planning aid, not emergency navigation.',
    };
  }
  if (maxRiskClass >= 2 || safeDepth >= 8) {
    return {
      label: 'ELEVATED FLOOD RISK',
      tone: 'red',
      guidance: 'Allow extra travel time and check the road exposure panel before leaving.',
    };
  }
  if (maxRiskClass >= 1 || safeDepth > 0) {
    return {
      label: 'MONITOR CONDITIONS',
      tone: 'amber',
      guidance: 'Some modelled cells show water exposure. Keep plans flexible and review the map at your chosen horizon.',
    };
  }
  return {
    label: 'LOW FLOOD RISK',
    tone: 'teal',
    guidance: 'The selected modelled surface shows no measurable flood exposure. Conditions can still change quickly during rain.',
  };
}

function rainfallAmount(rainfall: Record<string, unknown> | undefined) {
  if (!rainfall) return null;
  const candidateKeys = ['amount_mm', 'rainfall_mm', 'precipitation_mm', 'precip_mm', 'amount'];
  const candidate = candidateKeys.map((key) => rainfall[key]).find((value) => typeof value === 'number' && Number.isFinite(value));
  return typeof candidate === 'number' ? candidate : null;
}

function rainfallDescription(rainfall: Record<string, unknown> | undefined) {
  if (!rainfall) return 'Scenario description unavailable';
  return String(rainfall.description ?? rainfall.provider ?? 'Historical rainfall scenario');
}

function StatusPill({
  label,
  tone = 'teal',
  testId,
}: {
  label: string;
  tone?: 'teal' | 'amber' | 'red' | 'slate';
  testId: string;
}) {
  const toneClass = {
    teal: 'bg-[#d9efea] text-[#16645f]',
    amber: 'bg-[#fff0d1] text-[#8c5b16]',
    red: 'bg-[#f8dedb] text-[#98423d]',
    slate: 'bg-[#e3eaeb] text-[#50666b]',
  }[tone];
  const dotClass = {
    teal: 'bg-[#218c83]',
    amber: 'bg-[#c78b2e]',
    red: 'bg-[#b94c46]',
    slate: 'bg-[#718589]',
  }[tone];
  return (
    <span data-testid={testId} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.1em] ${toneClass}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />{label}
    </span>
  );
}

function SectionHeading({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
      <div>
        <div className="eyebrow text-[hsl(var(--primary))]">{eyebrow}</div>
        <h2 className="display-font mt-1 text-xl font-semibold tracking-[-.03em]">{title}</h2>
        {detail && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[hsl(var(--muted-foreground))]">{detail}</p>}
      </div>
      {action}
    </div>
  );
}

function StatCard({ label, value, hint, tone = 'teal' }: { label: string; value: string; hint: string; tone?: 'teal' | 'amber' | 'red' }) {
  return (
    <div data-testid={`stat-${label.toLowerCase().replaceAll(' ', '-')}`} className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.56)] p-3.5 transition-colors hover:border-[hsl(var(--primary)/.45)]">
      <div className={`h-1 w-10 rounded-full ${tone === 'red' ? 'bg-[#c4534d]' : tone === 'amber' ? 'bg-[#d19a38]' : 'bg-[#258e8d]'}`} />
      <div className="mt-3 text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">{label}</div>
      <div className="display-font mt-1 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-[10px] text-[hsl(var(--muted-foreground))]">{hint}</div>
    </div>
  );
}

function LoadingPanel({ label }: { label: string }) {
  return <div className="rounded-xl border border-dashed border-[#b8d0ca] bg-[#eff7f4] p-5 text-xs text-[#52716e]"><span className="skeleton mr-2 inline-block h-2 w-20 rounded-full" />Loading {label}…</div>;
}

function ErrorPanel({ label }: { label: string }) {
  return <div className="rounded-xl border border-[#e1b4ae] bg-[#fff3f0] p-5 text-xs text-[#98423d]"><AlertTriangle className="mr-2 inline-block h-4 w-4 align-text-bottom" />{label} unavailable. Check the API status before treating this view as current.</div>;
}

function PlaceSearchField({
  label,
  value,
  onChange,
  onSelect,
  selected,
  testId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onSelect: (result: PlaceSearchResult) => void;
  selected: PlaceSearchResult | null;
  testId: string;
}) {
  const [results, setResults] = useState<PlaceSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const query = value.trim();
    if (selected || query.length < 2) {
      setResults([]);
      setIsSearching(false);
      setSearchError('');
      abortRef.current?.abort();
      return;
    }
    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsSearching(true);
      setSearchError('');
      try {
        setResults(await searchHyderabadPlaces(query, controller.signal));
      } catch (error) {
        if ((error as { name?: string }).name !== 'AbortError') {
          setResults([]);
          setSearchError('Place search is unavailable. Try again or refine the location.');
        }
      } finally {
        if (!controller.signal.aborted) setIsSearching(false);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [selected, value]);

  return (
    <div className="relative">
      <label className="text-[10px] font-bold uppercase tracking-[.08em] text-[hsl(var(--muted-foreground))]">
        {label}
        <div className={`mt-1 flex items-center gap-2 rounded-lg border bg-[hsl(var(--background)/.6)] px-3 py-2.5 transition-colors ${selected ? 'border-[#258e8d]' : 'border-[hsl(var(--border))] focus-within:border-[#258e8d]'}`}>
          <Search className="h-3.5 w-3.5 shrink-0 text-[hsl(var(--muted-foreground))]" />
          <input
            data-testid={testId}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="Search Hyderabad places"
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-xs font-medium outline-none placeholder:text-[hsl(var(--muted-foreground)/.7)]"
          />
          {selected && <MapPin className="h-3.5 w-3.5 shrink-0 text-[#258e8d]" />}
        </div>
      </label>
      {!selected && value.trim().length >= 2 && (
        <div className="absolute inset-x-0 top-[4.3rem] z-20 overflow-hidden rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--popover))] shadow-xl">
          {isSearching && <div className="px-3 py-3 text-[11px] text-[hsl(var(--muted-foreground))]">Searching Hyderabad places…</div>}
          {!isSearching && searchError && <div className="px-3 py-3 text-[11px] text-[#e48c82]">{searchError}</div>}
          {!isSearching && !searchError && results.length === 0 && <div className="px-3 py-3 text-[11px] text-[hsl(var(--muted-foreground))]">No clear match. Try a landmark, suburb, or road.</div>}
          {!isSearching && results.map((result) => (
            <button
              key={result.id}
              type="button"
              data-testid={`result-place-${result.id}`}
              onClick={() => {
                onSelect(result);
                setResults([]);
              }}
              className="flex w-full items-start gap-2 border-b border-[hsl(var(--border)/.7)] px-3 py-2.5 text-left last:border-0 hover:bg-[hsl(var(--accent)/.12)]"
            >
              <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--primary))]" />
              <span className="min-w-0"><span className="block text-xs font-semibold">{result.label}</span><span className="mt-0.5 block truncate text-[10px] font-normal text-[hsl(var(--muted-foreground))]">{result.secondaryLabel} · {result.source}</span></span>
            </button>
          ))}
        </div>
      )}
      {selected && <div className="mt-1 text-[10px] text-[#63bdb0]">Selected: {selected.label}</div>}
    </div>
  );
}

function ForecastSummaryCard({
  query,
  selectedHorizon,
  onSelect,
}: {
  query: UseQueryResult<import('@workspace/api-client-react').ForecastSummaryResponse>;
  selectedHorizon: Horizon;
  onSelect: (value: Horizon) => void;
}) {
  if (query.isLoading) return <LoadingPanel label="forecast summary" />;
  if (query.isError || !query.data) return <ErrorPanel label="Flood outlook" />;
  const selected = query.data.horizons.find((item) => item.horizon_minutes === selectedHorizon) ?? query.data.horizons[0];
  const statistics = selected?.statistics;
  const riskCounts = statistics?.risk_class_counts ?? {};
  return (
    <div className="panel rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <div className="eyebrow text-[#26746d]">Rainfall outlook</div>
          <h3 className="display-font mt-1 text-lg font-semibold">Choose a forecast horizon</h3>
          <p data-testid="text-rainfall-source" className="mt-1 max-w-xl text-xs text-[hsl(var(--muted-foreground))]">{rainfallDescription(query.data.rainfall)}</p>
        </div>
        <div className="rounded-xl bg-[#173f47] px-4 py-3 text-right text-[#e5f2ed]">
          <div className="eyebrow text-[#9cc5bc]">Selected</div>
          <div className="display-font mt-1 text-2xl font-semibold">T+{selected?.horizon_minutes ?? selectedHorizon}<span className="ml-1 text-xs font-medium text-[#9cc5bc]">min</span></div>
        </div>
      </div>
      {selected && (
        <div className="mt-5 grid gap-3 lg:grid-cols-[1.15fr_.85fr]">
          <div className={`rounded-xl border p-4 ${deriveFloodOutlook(statistics).tone === 'red' ? 'border-[#8d4546] bg-[#351d25]' : deriveFloodOutlook(statistics).tone === 'amber' ? 'border-[#80642c] bg-[#302b1c]' : 'border-[#276b68] bg-[#173331]'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow text-[#9cc5bc]">Current flood outlook · T+{selected.horizon_minutes}</div>
                <div data-testid="status-flood-outlook" className="display-font mt-2 text-2xl font-semibold tracking-[-.04em] text-[#e5f2ed]">{deriveFloodOutlook(statistics).label}</div>
              </div>
              <StatusPill label={deriveFloodOutlook(statistics).tone === 'red' ? 'Review travel' : deriveFloodOutlook(statistics).tone === 'amber' ? 'Stay aware' : 'Clearer conditions'} tone={deriveFloodOutlook(statistics).tone} testId="status-flood-outlook-pill" />
            </div>
            <p data-testid="text-flood-guidance" className="mt-3 max-w-2xl text-xs leading-relaxed text-[#b6d2cc]">{deriveFloodOutlook(statistics).guidance}</p>
          </div>
          <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.48)] p-4">
            <div className="eyebrow text-[hsl(var(--muted-foreground))]">Rainfall scenario</div>
            <div data-testid="text-rainfall-amount" className="display-font mt-2 text-2xl font-semibold">{rainfallAmount(query.data.rainfall) === null ? 'N/A' : `${formatNumber(rainfallAmount(query.data.rainfall), 1)} mm`}</div>
            <p className="mt-1 text-[10px] leading-relaxed text-[hsl(var(--muted-foreground))]">Amount reported by the API. When no numeric amount is supplied, the source description above is the scenario used.</p>
          </div>
        </div>
      )}
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
        {horizons.map((minutes) => (
          <button
            key={minutes}
            data-testid={`button-horizon-${minutes}`}
            onClick={() => onSelect(minutes)}
            className={`rounded-lg border px-2 py-2.5 text-xs font-bold transition-colors ${selected?.horizon_minutes === minutes ? 'border-[#258e8d] bg-[#d9efea] text-[#16645f]' : 'border-[hsl(var(--border))] bg-[hsl(var(--background)/.55)] text-[hsl(var(--muted-foreground))] hover:border-[#8db9b2]'}`}
          >
            T+{minutes}
          </button>
        ))}
      </div>
      <div data-testid="forecast-timeline" className="mt-5 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.44)] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">Forecast progression</div>
          <div className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">0 → 180 MIN</div>
        </div>
        <div className="grid grid-cols-7 gap-2">
          {horizons.map((minutes) => {
            const item = query.data.horizons.find((horizon) => horizon.horizon_minutes === minutes);
            const depth = Number(item?.statistics.maximum_depth_cm ?? 0);
            const peak = Math.max(...query.data.horizons.map((horizon) => Number(horizon.statistics.maximum_depth_cm ?? 0)), 1);
            const selectedBar = minutes === selected?.horizon_minutes;
            return (
              <button key={minutes} data-testid={`timeline-horizon-${minutes}`} onClick={() => onSelect(minutes)} className="group min-w-0 text-left">
                <div className="flex h-16 items-end rounded-md bg-[hsl(var(--muted)/.7)] p-1">
                  <span className={`block w-full rounded-sm transition-all duration-300 ${selectedBar ? 'bg-[hsl(var(--primary))]' : 'bg-[hsl(var(--primary)/.38)] group-hover:bg-[hsl(var(--primary)/.7)]'}`} style={{ height: `${Math.max(10, (depth / peak) * 100)}%` }} />
                </div>
                <div className={`mt-2 text-center font-mono text-[9px] ${selectedBar ? 'text-[hsl(var(--primary))]' : 'text-[hsl(var(--muted-foreground))]'}`}>T+{minutes}</div>
              </button>
            );
          })}
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <StatCard label="Maximum depth" value={`${formatNumber(statistics?.maximum_depth_cm)} cm`} hint="screening surface" tone={Number(statistics?.maximum_depth_cm ?? 0) > 15 ? 'red' : 'amber'} />
        <StatCard label="Mean depth" value={`${formatNumber(statistics?.mean_depth_cm, 2)} cm`} hint="valid cells" />
        <StatCard label="Affected cells" value={String(statistics?.affected_cell_count ?? '—')} hint="depth > 0" />
        <StatCard label="Scenario factor" value={formatNumber(selected?.persistence_decay_factor, 3)} hint="relative to T+0" />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[hsl(var(--border))] pt-3 text-[10px] text-[hsl(var(--muted-foreground))]">
        <span>{selected?.rainfall_scenario ?? 'Persistence/decay projection of Step 6 baseline.'}</span>
        <span className="font-mono">Updated {new Date(query.data.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Calcutta' })} IST</span>
      </div>
      <div className="mt-4">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">Risk classes · selected horizon</div>
        <div className="flex h-2 overflow-hidden rounded-full bg-[#dfeae7]">
          {[0, 1, 2, 3, 4].map((risk) => {
            const total = Object.values(riskCounts).reduce((sum, value) => sum + Number(value), 0) || 1;
            return <span key={risk} style={{ width: `${(Number(riskCounts[String(risk)] ?? 0) / total) * 100}%`, backgroundColor: riskColors[risk] }} />;
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[hsl(var(--muted-foreground))]">
          {[0, 1, 2, 3, 4].map((risk) => <span key={risk}><i className="mr-1 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: riskColors[risk] }} />{riskLabel(risk)} {Number(riskCounts[String(risk)] ?? 0).toLocaleString()}</span>)}
        </div>
      </div>
    </div>
  );
}

const riskColors: Record<number, string> = { 0: '#9ec9c2', 1: '#f0c96d', 2: '#e5944f', 3: '#cf5d50', 4: '#8f2d35' };

function RouteResults({ route }: { route: import('@workspace/api-client-react').SafeRouteResponse }) {
  const cards: Array<{ title: string; data: RouteSummary; accent: string }> = [
    { title: 'Normal Route', data: route.normal_route, accent: '#718589' },
    { title: 'Flood-Aware Route', data: route.flood_safe_route, accent: '#258e8d' },
  ];
  const normal = route.normal_route;
  const floodAware = route.flood_safe_route;
  const identical = normal.distance_m === floodAware.distance_m
    && normal.estimated_time_min === floodAware.estimated_time_min
    && normal.max_flood_depth_cm === floodAware.max_flood_depth_cm
    && normal.max_risk_class === floodAware.max_risk_class;
  const lowerExposure = floodAware.max_risk_class < normal.max_risk_class || floodAware.max_flood_depth_cm < normal.max_flood_depth_cm;
  const bothLowExposure = normal.max_risk_class <= 1 && floodAware.max_risk_class <= 1
    && normal.max_flood_depth_cm < 5 && floodAware.max_flood_depth_cm < 5;
  const recommendation = identical
    ? 'No significant flood-related detour was required for this screening.'
    : lowerExposure
      ? 'Prototype screening recommends the flood-aware route because its returned flood exposure is lower.'
      : bothLowExposure
        ? 'Both routes show low returned flood exposure; choose based on distance and travel time.'
        : 'Both routes retain meaningful returned exposure. Reconsider travel and check conditions before leaving.';
  return (
    <div>
      <div data-testid="text-route-recommendation" className="mb-3 rounded-lg border border-[#80642c] bg-[#302b1c] px-3 py-2.5 text-[11px] leading-relaxed text-[#e7c982]"><span className="font-bold uppercase tracking-[.08em]">Prototype screening · </span>{recommendation}</div>
      <div className="grid gap-3 md:grid-cols-2">
      {cards.map((card) => (
        <div key={card.title} data-testid={`card-route-${card.title.toLowerCase().replaceAll(' ', '-')}`} className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.5)] p-4">
          <div className="flex items-center justify-between"><div className="text-xs font-bold">{card.title}</div><span className="h-2 w-8 rounded-full" style={{ backgroundColor: card.accent }} /></div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <StatCard label="Distance" value={formatDistance(card.data.distance_m)} hint={`${formatNumber(card.data.estimated_time_min)} min estimated`} />
            <StatCard label="Max depth" value={`${formatNumber(card.data.max_flood_depth_cm)} cm`} hint={`${riskLabel(card.data.max_risk_class)} risk`} tone={card.data.max_risk_class >= 3 ? 'red' : card.data.max_risk_class >= 2 ? 'amber' : 'teal'} />
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px] text-[hsl(var(--muted-foreground))]"><span>Route screening</span><StatusPill label={card.data.safety} tone={riskTone(card.data.max_risk_class)} testId={`status-route-${card.title.replaceAll(' ', '-').toLowerCase()}`} /></div>
        </div>
      ))}
      </div>
    </div>
  );
}

function ModelInformation() {
  return (
    <details className="panel rounded-2xl p-5 sm:p-6">
      <summary data-testid="button-about-prototype" className="flex cursor-pointer list-none items-center justify-between gap-4">
        <span><span className="eyebrow text-[hsl(var(--primary))]">About this prototype</span><span className="mt-1 block text-sm font-semibold">Sources, model stages, and limits</span></span>
        <Info className="h-4 w-4 shrink-0 text-[hsl(var(--muted-foreground))]" />
      </summary>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ['Rainfall', 'IMD historical gridded rainfall'],
          ['Terrain', 'SRTM 30m DEM'],
          ['Land cover', 'ESA WorldCover 10m'],
          ['Drainage', 'GHMC / Telangana GIS datasets'],
          ['Forecast', 'Deterministic 0–3 hour persistence / decay scenario'],
          ['Routing', 'Flood-aware road screening with prototype risk penalties'],
        ].map(([label, value]) => <div key={label} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.52)] p-3"><div className="text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">{label}</div><div className="mt-1 text-xs font-semibold">{value}</div></div>)}
      </div>
      <p className="mt-4 border-t border-[hsl(var(--border))] pt-4 text-[11px] leading-relaxed text-[hsl(var(--muted-foreground))]">Research prototype for flood-awareness and route-screening demonstrations. It is not live radar nowcasting, an emergency warning, or a substitute for official advisories and on-ground judgement. Do not use these depths or routes for emergency navigation or engineering decisions.</p>
    </details>
  );
}

function Home() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [selectedHorizon, setSelectedHorizon] = useState<Horizon>(60);
  const [lastRefresh, setLastRefresh] = useState('Not synced');
  const [selectedRoad, setSelectedRoad] = useState<GeoFeature | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [visibility, setVisibility] = useState<LayerVisibility>({ flood: true, roads: true, nalas: true, waterbodies: true, boundary: true });
  const [routeRequested, setRouteRequested] = useState(false);
  const [sourceQuery, setSourceQuery] = useState('');
  const [destinationQuery, setDestinationQuery] = useState('');
  const [sourcePlace, setSourcePlace] = useState<PlaceSearchResult | null>(null);
  const [destinationPlace, setDestinationPlace] = useState<PlaceSearchResult | null>(null);
  const [routeInputError, setRouteInputError] = useState('');
  const [routeParams, setRouteParams] = useState({
    source_lat: 17.5029521,
    source_lon: 78.4617008,
    destination_lat: 17.3142495,
    destination_lon: 78.4686587,
    forecast_minutes: 60 as Horizon,
  });

  const systemStatus = useGetSystemStatus({ query: { queryKey: getGetSystemStatusQueryKey() } });
  const health = useGetHealth({ query: { queryKey: getGetHealthQueryKey() } });
  const forecastStatus = useGetForecastStatus({ query: { queryKey: getGetForecastStatusQueryKey() } });
  const forecastSummary = useGetForecastSummary({ query: { queryKey: getGetForecastSummaryQueryKey() } });
  const mapLayers = useGetMapLayers({ forecast_minutes: selectedHorizon }, { query: { queryKey: getGetMapLayersQueryKey({ forecast_minutes: selectedHorizon }), staleTime: 60_000 } });
  const dataStatus = useGetDataStatus({ query: { queryKey: getGetDataStatusQueryKey() } });
  const preprocessing = useGetPreprocessingStatus({ query: { queryKey: getGetPreprocessingStatusQueryKey() } });
  const safeRoute = useGetSafeRoute(routeParams, { query: { enabled: routeRequested, queryKey: getGetSafeRouteQueryKey(routeParams) } });

  const onRoadSelect = useCallback((feature: GeoFeature | null) => setSelectedRoad(feature), []);
  const routeLines = useMemo<RouteLine[]>(() => {
    if (!safeRoute.data) return [];
    return [
      { points: safeRoute.data.normal_route.route, color: '#6f8588', weight: 4, dashArray: '7 6' },
      { points: safeRoute.data.flood_safe_route.route, color: '#167f79', weight: 5 },
    ];
  }, [safeRoute.data]);

  const refreshAll = async () => {
    await Promise.all([systemStatus.refetch(), health.refetch(), forecastStatus.refetch(), forecastSummary.refetch(), mapLayers.refetch(), dataStatus.refetch(), preprocessing.refetch(), routeRequested ? safeRoute.refetch() : Promise.resolve()]);
    setLastRefresh(`${new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Calcutta' }).format(new Date())} IST`);
  };
  const scrollTo = (target: string) => {
    setMobileNavOpen(false);
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const toggleLayer = (key: keyof LayerVisibility) => setVisibility((current) => ({ ...current, [key]: !current[key] }));
  const selectedRoadProperties = selectedRoad?.properties ?? {};
  const systemReady = !systemStatus.isError && !health.isError && forecastStatus.data?.status === 'ready';
  const selectedForecast = forecastSummary.data?.horizons.find((item) => item.horizon_minutes === selectedHorizon);
  const currentOutlook = deriveFloodOutlook(selectedForecast?.statistics);

  const navItems = [
    { id: 'dashboard', label: 'Flood map', icon: Map },
    { id: 'forecast', label: 'Forecast', icon: BarChart3 },
    { id: 'routing', label: 'Find a safer route', icon: RouteIcon },
    { id: 'sources', label: 'About this prototype', icon: Info },
  ];

  return (
    <div className="app-shell min-h-[100dvh]">
      <aside className={`sidebar-grid fixed inset-y-0 left-0 z-40 w-[258px] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] transition-transform duration-300 md:translate-x-0 ${mobileNavOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex h-full flex-col overflow-y-auto">
          <div className="flex items-start justify-between border-b border-[hsl(var(--sidebar-border))] px-5 py-5">
            <button onClick={() => scrollTo('dashboard')} className="text-left"><div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[hsl(var(--sidebar-primary))] text-[#173d42]"><Droplets className="h-4 w-4" /></span><span className="display-font text-sm font-bold">HYD · NOWCAST</span></div><p className="mt-3 pl-10 text-[9px] uppercase tracking-[.16em] text-[#a7c4c2]">Urban resilience desk</p></button>
            <button onClick={() => setMobileNavOpen(false)} className="rounded-md p-1 text-[#b0ccca] md:hidden"><X className="h-4 w-4" /></button>
          </div>
          <div className="border-b border-[hsl(var(--sidebar-border))] px-4 py-4">
            <div className="flex items-center justify-between"><div className="text-[10px] font-bold uppercase tracking-[.12em] text-[#a6c5c2]">System status</div><StatusPill label={systemReady ? 'ready' : systemStatus.isError ? 'offline' : 'checking'} tone={systemReady ? 'teal' : 'amber'} testId="sidebar-system-status" /></div>
            <div className="mt-2 text-[10px] leading-relaxed text-[#91b2b0]">Prototype signals only · not an emergency warning.</div>
          </div>
          <div className="px-4 py-5">
            <div className="eyebrow px-1 pb-2 text-[#88aaa8]">Forecast horizon</div>
            <div className="grid grid-cols-2 gap-1.5">
              {horizons.map((minutes) => <button key={minutes} data-testid={`sidebar-horizon-${minutes}`} onClick={() => setSelectedHorizon(minutes)} className={`rounded-md px-2 py-2 text-[11px] font-bold ${selectedHorizon === minutes ? 'bg-[#d9efea] text-[#16645f]' : 'bg-[hsl(var(--sidebar-accent))] text-[#b5ccca] hover:text-white'}`}>T+{minutes}</button>)}
            </div>
          </div>
          <div className="border-t border-[hsl(var(--sidebar-border))] px-4 py-5">
            <div className="eyebrow px-1 pb-2 text-[#88aaa8]">Map layers</div>
            <div className="space-y-1.5">
              {layerLabels.map((layer) => <button key={layer.key} data-testid={`toggle-layer-${layer.key}`} onClick={() => toggleLayer(layer.key)} className="flex w-full items-center gap-2 rounded-md px-1 py-2 text-left text-[11px] text-[#b5ccca] hover:bg-[hsl(var(--sidebar-accent))]"><span className={`flex h-4 w-4 items-center justify-center rounded border ${visibility[layer.key] ? 'border-[#8dc5bc] bg-[#d9efea]' : 'border-[#648887]'}`}>{visibility[layer.key] && <Check className="h-3 w-3 text-[#167269]" />}</span><span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} /><span>{layer.label}</span></button>)}
            </div>
          </div>
          <div className="border-t border-[hsl(var(--sidebar-border))] px-4 py-5">
            <div className="eyebrow px-1 pb-2 text-[#88aaa8]">Command view</div>
            <nav className="space-y-1">{navItems.map(({ id, label, icon: Icon }) => <button key={id} data-testid={`nav-${id}`} onClick={() => scrollTo(id)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left text-xs font-semibold text-[#b5ccca] hover:bg-[hsl(var(--sidebar-accent))] hover:text-white"><Icon className="h-4 w-4" /><span>{label}</span><ChevronRight className="ml-auto h-3 w-3 opacity-50" /></button>)}</nav>
          </div>
          <div className="mt-auto border-t border-[hsl(var(--sidebar-border))] p-4"><div className="rounded-lg border border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-accent)/.55)] p-3"><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.12em] text-[#a6c5c2]"><ShieldCheck className="h-3.5 w-3.5 text-[#f0c96d]" /> Prototype boundary</div><p className="mt-2 text-[10px] leading-relaxed text-[#91b2b0]">Historical rainfall scenario, modelled depth, and route screening only.</p></div><div className="mt-4 flex items-center justify-between text-[10px] text-[#7e9f9e]"><span>Research prototype</span><span className="mono-font">HYD-01</span></div></div>
        </div>
      </aside>
      {mobileNavOpen && <button aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} className="fixed inset-0 z-30 bg-[#113841]/30 md:hidden" />}
      <main className="min-h-[100dvh] md:pl-[258px]">
        <header className="sticky top-0 z-20 border-b border-[hsl(var(--border)/.8)] bg-[hsl(var(--background)/.9)] px-4 py-3 backdrop-blur-xl sm:px-6 lg:px-9">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
            <div className="flex items-center gap-3"><button onClick={() => setMobileNavOpen(true)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 md:hidden"><Menu className="h-4 w-4" /></button><div><div className="eyebrow text-[hsl(var(--muted-foreground))]">MONSOON OPERATIONS · 0–3 HOURS</div><h1 className="display-font mt-0.5 text-lg font-semibold tracking-[-.03em]">Hyderabad Flood Intelligence</h1><div className="mt-0.5 text-[11px] text-[hsl(var(--muted-foreground))]">Flood outlook, road conditions, and safer route screening</div></div></div>
            <div className="flex items-center gap-2 sm:gap-4"><div className="hidden text-right sm:block"><div className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">LAST SYNC</div><div data-testid="text-last-sync" className="mono-font mt-0.5 text-xs">{lastRefresh}</div></div><button data-testid="button-refresh" onClick={refreshAll} className="flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))] shadow-sm"><RefreshCw className={`h-3.5 w-3.5 ${[systemStatus, health, forecastStatus, forecastSummary, mapLayers, dataStatus, preprocessing, safeRoute].some((query) => query.isFetching) ? 'animate-spin' : ''}`} /><span className="hidden sm:inline">Refresh</span></button><StatusPill label="PROTOTYPE" tone="amber" testId="header-prototype-badge" /><div className="relative"><button data-testid="button-system-notice" onClick={() => setNoticeOpen((value) => !value)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 text-[hsl(var(--primary))]"><Activity className="h-4 w-4" /></button>{noticeOpen && <div data-testid="panel-system-notice" className="absolute right-0 top-11 z-30 w-72 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4 text-xs shadow-xl"><div className="font-bold">System notice</div><p className="mt-2 leading-relaxed text-[hsl(var(--muted-foreground))]">This view uses historical IMD gridded rainfall and deterministic persistence/decay. It is not live radar nowcasting.</p></div>}</div></div>
          </div>
        </header>
        <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 lg:px-9 lg:py-8">
          <section id="dashboard" data-testid="section-dashboard" className="scroll-mt-24">
            <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><div className="eyebrow text-[hsl(var(--primary))]">Flood map · Hyderabad</div><h2 className="display-font mt-2 max-w-3xl text-3xl font-semibold leading-[1.05] tracking-[-.055em] sm:text-5xl">Know the outlook.<br /><span className="text-[hsl(var(--primary))]">Plan the next trip.</span></h2><p className="mt-3 max-w-2xl text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Check the selected rainfall scenario, see where water may affect roads, and screen a lower-exposure route across Hyderabad.</p></div><div className="flex items-center gap-2"><StatusPill label={systemReady ? 'DATA READY' : 'CHECKING'} tone={systemReady ? 'teal' : 'amber'} testId="status-system" /><StatusPill label={health.data?.status ?? 'API'} tone={health.isError ? 'red' : 'teal'} testId="status-api" /></div></div>
            <div className="mb-4 rounded-xl border border-[#d7c697] bg-[#fff8e8] px-4 py-3 text-xs text-[#725b2d]"><div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#b17c21]" /><p><strong className="font-bold">Prototype boundary.</strong> This prototype uses historical IMD gridded rainfall and a deterministic persistence/decay scenario for 0–3 hour forecasting. Operational Doppler Weather Radar nowcasts and authoritative drainage/hydraulic parameters are future integrations. Flood depths and routes must not be used for emergency navigation or engineering decisions.</p></div></div>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_360px]">
              <div className="panel rounded-2xl p-2 sm:p-3"><LeafletMap data={mapLayers.data} visibility={visibility} routes={routeLines} onRoadSelect={onRoadSelect} /></div>
              <aside className="panel rounded-2xl p-5">
                <div className="flex items-center justify-between"><div><div className="eyebrow text-[#26746d]">Road conditions</div><h3 className="display-font mt-1 text-xl font-semibold">Flood outlook</h3></div><Waves className="h-5 w-5 text-[#258e8d]" /></div>
                {forecastSummary.data && <div className="mt-5 rounded-xl bg-[#173f47] p-4 text-[#e5f2ed]"><div className="eyebrow text-[#9cc5bc]">Selected horizon · T+{selectedHorizon}</div><div data-testid="map-status-flood-outlook" className="display-font mt-2 text-2xl font-semibold">{currentOutlook.label}</div><div className="mt-2 text-[10px] leading-relaxed text-[#b6d2cc]">{currentOutlook.guidance}</div></div>}
                <div className="mt-4 space-y-2">{mapLayers.isLoading ? <LoadingPanel label="map layers" /> : mapLayers.isError ? <ErrorPanel label="Map layers" /> : <><StatCard label="Maximum depth" value={`${formatNumber(selectedForecast?.statistics.maximum_depth_cm)} cm`} hint="selected forecast" tone={Number(selectedForecast?.statistics.maximum_depth_cm ?? 0) > 15 ? 'red' : 'amber'} /><StatCard label="Road layer" value={visibility.roads ? 'Visible' : 'Hidden'} hint="click a road for details" /><StatCard label="Map grid" value={String(mapLayers.data?.limits?.flood_grid ?? '80×60')} hint="simplified web overlay" /></>}</div>
                <div className="mt-5 border-t border-[hsl(var(--border))] pt-4"><div className="mb-3 text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">Flood risk legend</div><div className="grid grid-cols-2 gap-2">{[0, 1, 2, 3].map((risk) => <div key={risk} className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))]"><span className="h-3 w-3 rounded-sm" style={{ backgroundColor: riskColors[risk] }} />{riskLabel(risk)}</div>)}</div></div>
                {selectedRoad && <div className="mt-5 rounded-xl border border-[#b8d0ca] bg-[#eff7f4] p-4"><div className="eyebrow text-[#26746d]">Selected road</div><div className="mt-1 text-sm font-bold">{String(selectedRoadProperties.name ?? 'Unnamed road')}</div><div className="mt-3 grid grid-cols-2 gap-2 text-[10px]"><span>Forecast depth<br /><b className="text-sm">{formatNumber(selectedRoadProperties.forecast_max_depth_cm)} cm</b></span><span>Risk<br /><b className="text-sm">{riskLabel(Number(selectedRoadProperties.forecast_risk_class ?? 0))}</b></span><span>Mean depth<br /><b className="text-sm">{formatNumber(selectedRoadProperties.forecast_mean_depth_cm)} cm</b></span><span>Horizon<br /><b className="text-sm">T+{selectedHorizon}</b></span></div></div>}
                <div className="mt-5 text-[10px] leading-relaxed text-[hsl(var(--muted-foreground))]">Map layers are simplified for browser performance. The original GeoTIFFs and full road graph remain server-side.</div>
              </aside>
            </div>
          </section>

           <section id="forecast" data-testid="section-forecast" className="scroll-mt-24"><SectionHeading eyebrow="01 · Rainfall outlook" title="Flood outlook" detail="Choose T+0 through T+180 to update the map, surface statistics, road exposure, and route screening context." action={<StatusPill label={forecastStatus.data?.status ?? 'checking'} tone={forecastStatus.data?.status === 'ready' ? 'teal' : 'amber'} testId="status-forecast" />} /><ForecastSummaryCard query={forecastSummary} selectedHorizon={selectedHorizon} onSelect={setSelectedHorizon} /></section>

            <section id="routing" data-testid="section-routing" className="scroll-mt-24"><SectionHeading eyebrow="02 · Decision support" title="Find a safer route" detail="Choose two places in Hyderabad to compare the normal route with a flood-aware route at your selected forecast horizon." action={<StatusPill label={safeRoute.isError ? 'unavailable' : safeRoute.data ? safeRoute.data.safety : 'ready to query'} tone={safeRoute.isError ? 'red' : safeRoute.data?.safety === 'SAFE' ? 'teal' : 'amber'} testId="status-safe-route" />} /><div className="panel rounded-2xl p-5 sm:p-6"><div className="grid gap-5 lg:grid-cols-[1fr_1.3fr]"><div><div className="flex items-center gap-3"><div className="rounded-xl bg-[#d9efea] p-3 text-[#167269]"><Navigation className="h-5 w-5" /></div><div><div className="text-sm font-bold">Screen a flood-aware trip</div><div className="text-[10px] text-[hsl(var(--muted-foreground))]">Search and select a Hyderabad place for each point</div></div></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><PlaceSearchField label="From" value={sourceQuery} selected={sourcePlace} onChange={(value) => { setSourceQuery(value); setSourcePlace(null); setRouteInputError(''); }} onSelect={(result) => { setSourceQuery(result.label); setSourcePlace(result); setRouteInputError(''); setRouteParams((current) => ({ ...current, source_lat: result.lat, source_lon: result.lon })); }} testId="input-route-source_lat" /><PlaceSearchField label="To" value={destinationQuery} selected={destinationPlace} onChange={(value) => { setDestinationQuery(value); setDestinationPlace(null); setRouteInputError(''); }} onSelect={(result) => { setDestinationQuery(result.label); setDestinationPlace(result); setRouteInputError(''); setRouteParams((current) => ({ ...current, destination_lat: result.lat, destination_lon: result.lon })); }} testId="input-route-destination_lat" /></div>{routeInputError && <div data-testid="status-route-input-error" className="mt-3 rounded-lg border border-[#80642c] bg-[#302b1c] px-3 py-2 text-[11px] text-[#e7c982]">{routeInputError}</div>}<div className="mt-4"><div className="mb-2 text-[10px] font-bold uppercase tracking-[.08em] text-[hsl(var(--muted-foreground))]">Route horizon</div><div className="grid grid-cols-4 gap-1.5 sm:grid-cols-7">{horizons.map((minutes) => <button key={minutes} data-testid={`route-horizon-${minutes}`} onClick={() => setRouteParams((current) => ({ ...current, forecast_minutes: minutes }))} className={`rounded-md border px-1 py-2 text-[10px] font-bold ${routeParams.forecast_minutes === minutes ? 'border-[#258e8d] bg-[#d9efea] text-[#16645f]' : 'border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]'}`}>T+{minutes}</button>)}</div></div><button data-testid="button-find-route" onClick={() => { if (!sourcePlace || !destinationPlace) { setRouteInputError('Select one clear result for both From and To before screening a route.'); return; } setRouteInputError(''); setRouteRequested(true); }} className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-[#1a7174] px-4 py-3 text-xs font-bold text-white shadow-sm hover:bg-[#145e63]"><RouteIcon className="h-4 w-4" /> FIND SAFER ROUTE</button>{safeRoute.isLoading && <div data-testid="status-route-loading" className="mt-3 text-xs text-[hsl(var(--muted-foreground))]">Comparing normal and flood-aware routes…</div>}{safeRoute.isError && <div data-testid="status-route-error" className="mt-3 text-xs text-[#98423d]">Unable to calculate this route. Try another selected place within the Hyderabad road graph.</div>}</div><div>{safeRoute.data ? <RouteResults route={safeRoute.data} /> : <div className="flex h-full min-h-[230px] items-center justify-center rounded-xl border border-dashed border-[#b8d0ca] bg-[#eff7f4] p-6 text-center"><div><RouteIcon className="mx-auto h-7 w-7 text-[#5b9e99]" /><div className="mt-3 text-sm font-bold text-[#356f6b]">Route comparison ready</div><p className="mt-1 max-w-sm text-[11px] leading-relaxed text-[#6d8587]">Select a From place, a To place, and a horizon to draw both routes on the map and compare returned flood exposure.</p></div></div>}</div></div></div></section>

           <section id="sources" data-testid="section-sources" className="scroll-mt-24"><ModelInformation /></section>

           <footer className="flex flex-col justify-between gap-3 border-t border-[hsl(var(--border))] pb-8 pt-5 text-[10px] text-[hsl(var(--muted-foreground))] sm:flex-row"><span>Research prototype · historical rainfall scenario · no live radar · no emergency navigation</span><span className="mono-font">HYD / FLOOD INTELLIGENCE</span></footer>
        </div>
      </main>
    </div>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function Router() {
  return <RoutedErrorBoundary><Switch><Route path="/" component={Home} /><Route component={NotFound} /></Switch></RoutedErrorBoundary>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;