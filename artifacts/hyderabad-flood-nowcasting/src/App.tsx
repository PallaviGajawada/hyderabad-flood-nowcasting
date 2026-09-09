import { useCallback, useMemo, useState, type ReactNode } from 'react';
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
  CloudRain,
  Database,
  Droplets,
  Gauge,
  GitBranch,
  Layers3,
  Map,
  Menu,
  Navigation,
  RefreshCw,
  Route as RouteIcon,
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
import type {
  DatasetStatus,
  ForecastHorizonSummary,
  GetSafeRouteForecastMinutes,
  MapLayersResponse,
  RouteSummary,
} from '@workspace/api-client-react';
import { Route, Router as WouterRouter, Switch, useLocation } from 'wouter';
import NotFound from '@/pages/not-found';

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
    <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.56)] p-3.5">
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
  if (query.isError || !query.data) return <ErrorPanel label="Forecast summary" />;
  const selected = query.data.horizons.find((item) => item.horizon_minutes === selectedHorizon) ?? query.data.horizons[0];
  const statistics = selected?.statistics;
  const riskCounts = statistics?.risk_class_counts ?? {};
  return (
    <div className="panel rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <div className="eyebrow text-[#26746d]">Forecast horizon</div>
          <h3 className="display-font mt-1 text-lg font-semibold">Scenario surface selector</h3>
          <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">{String(query.data.rainfall?.description ?? 'Historical IMD gridded rainfall · prototype scenario')}</p>
        </div>
        <div className="rounded-xl bg-[#173f47] px-4 py-3 text-right text-[#e5f2ed]">
          <div className="eyebrow text-[#9cc5bc]">Selected</div>
          <div className="display-font mt-1 text-2xl font-semibold">T+{selected?.horizon_minutes ?? selectedHorizon}<span className="ml-1 text-xs font-medium text-[#9cc5bc]">min</span></div>
        </div>
      </div>
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
    { title: 'Normal route', data: route.normal_route, accent: '#718589' },
    { title: 'Flood-safe route', data: route.flood_safe_route, accent: '#258e8d' },
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {cards.map((card) => (
        <div key={card.title} className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background)/.5)] p-4">
          <div className="flex items-center justify-between"><div className="text-xs font-bold">{card.title}</div><span className="h-2 w-8 rounded-full" style={{ backgroundColor: card.accent }} /></div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <StatCard label="Distance" value={formatDistance(card.data.distance_m)} hint={`${formatNumber(card.data.estimated_time_min)} min estimated`} />
            <StatCard label="Max depth" value={`${formatNumber(card.data.max_flood_depth_cm)} cm`} hint={`${riskLabel(card.data.max_risk_class)} risk`} tone={card.data.max_risk_class >= 3 ? 'red' : card.data.max_risk_class >= 2 ? 'amber' : 'teal'} />
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px] text-[hsl(var(--muted-foreground))]"><span>Route screening</span><StatusPill label={card.data.safety} tone={riskTone(card.data.max_risk_class)} testId={`status-route-${card.title.replaceAll(' ', '-').toLowerCase()}`} /></div>
        </div>
      ))}
    </div>
  );
}

function ModelInformation() {
  return (
    <div className="panel rounded-2xl p-5 sm:p-6">
      <SectionHeading eyebrow="04 · Model information" title="Know what the map is showing" detail="Inputs and assumptions remain visible so a demonstration never looks more certain than the science." />
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ['Rainfall', 'IMD historical gridded rainfall'],
          ['Terrain', 'SRTM 30m DEM'],
          ['Land cover', 'ESA WorldCover 10m'],
          ['Drainage', 'GHMC / Telangana GIS drainage datasets'],
          ['Forecast', '0–3 hour deterministic prototype forecast'],
          ['Routing', 'Flood-aware road routing using prototype flood-risk penalties'],
        ].map(([label, value]) => <div key={label} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.52)] p-3"><div className="text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">{label}</div><div className="mt-1 text-xs font-semibold">{value}</div></div>)}
      </div>
    </div>
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

  const navItems = [
    { id: 'dashboard', label: 'Live map', icon: Map },
    { id: 'forecast', label: 'Forecast', icon: BarChart3 },
    { id: 'routing', label: 'Flood-safe route', icon: RouteIcon },
    { id: 'sources', label: 'Model information', icon: Database },
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
              {horizons.map((minutes) => <button key={minutes} onClick={() => setSelectedHorizon(minutes)} className={`rounded-md px-2 py-2 text-[11px] font-bold ${selectedHorizon === minutes ? 'bg-[#d9efea] text-[#16645f]' : 'bg-[hsl(var(--sidebar-accent))] text-[#b5ccca] hover:text-white'}`}>T+{minutes}</button>)}
            </div>
          </div>
          <div className="border-t border-[hsl(var(--sidebar-border))] px-4 py-5">
            <div className="eyebrow px-1 pb-2 text-[#88aaa8]">Map layers</div>
            <div className="space-y-1.5">
              {layerLabels.map((layer) => <button key={layer.key} onClick={() => toggleLayer(layer.key)} className="flex w-full items-center gap-2 rounded-md px-1 py-2 text-left text-[11px] text-[#b5ccca] hover:bg-[hsl(var(--sidebar-accent))]"><span className={`flex h-4 w-4 items-center justify-center rounded border ${visibility[layer.key] ? 'border-[#8dc5bc] bg-[#d9efea]' : 'border-[#648887]'}`}>{visibility[layer.key] && <Check className="h-3 w-3 text-[#167269]" />}</span><span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} /><span>{layer.label}</span></button>)}
            </div>
          </div>
          <div className="border-t border-[hsl(var(--sidebar-border))] px-4 py-5">
            <div className="eyebrow px-1 pb-2 text-[#88aaa8]">Command view</div>
            <nav className="space-y-1">{navItems.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => scrollTo(id)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left text-xs font-semibold text-[#b5ccca] hover:bg-[hsl(var(--sidebar-accent))] hover:text-white"><Icon className="h-4 w-4" /><span>{label}</span><ChevronRight className="ml-auto h-3 w-3 opacity-50" /></button>)}</nav>
          </div>
          <div className="mt-auto border-t border-[hsl(var(--sidebar-border))] p-4"><div className="rounded-lg border border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-accent)/.55)] p-3"><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.12em] text-[#a6c5c2]"><ShieldCheck className="h-3.5 w-3.5 text-[#f0c96d]" /> Trust boundary</div><p className="mt-2 text-[10px] leading-relaxed text-[#91b2b0]">Historical IMD scenario, prototype depth, and route screening only.</p></div><div className="mt-4 flex items-center justify-between text-[10px] text-[#7e9f9e]"><span>Step 8 demo</span><span className="mono-font">HYD-01</span></div></div>
        </div>
      </aside>
      {mobileNavOpen && <button aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} className="fixed inset-0 z-30 bg-[#113841]/30 md:hidden" />}
      <main className="min-h-[100dvh] md:pl-[258px]">
        <header className="sticky top-0 z-20 border-b border-[hsl(var(--border)/.8)] bg-[hsl(var(--background)/.9)] px-4 py-3 backdrop-blur-xl sm:px-6 lg:px-9">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
            <div className="flex items-center gap-3"><button onClick={() => setMobileNavOpen(true)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 md:hidden"><Menu className="h-4 w-4" /></button><div><div className="eyebrow text-[hsl(var(--muted-foreground))]">MONSOON OPERATIONS · 0–3 HOURS</div><h1 className="display-font mt-0.5 text-lg font-semibold tracking-[-.03em]">Hyderabad Urban Flood Nowcasting</h1><div className="mt-0.5 text-[11px] text-[hsl(var(--muted-foreground))]">0–3 Hour Urban Flood Forecast & Flood-Safe Routing</div></div></div>
            <div className="flex items-center gap-2 sm:gap-4"><div className="hidden text-right sm:block"><div className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">LAST SYNC</div><div className="mono-font mt-0.5 text-xs">{lastRefresh}</div></div><button onClick={refreshAll} className="flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))] shadow-sm"><RefreshCw className={`h-3.5 w-3.5 ${[systemStatus, health, forecastStatus, forecastSummary, mapLayers, dataStatus, preprocessing, safeRoute].some((query) => query.isFetching) ? 'animate-spin' : ''}`} /><span className="hidden sm:inline">Refresh</span></button><StatusPill label="PROTOTYPE" tone="amber" testId="header-prototype-badge" /><div className="relative"><button onClick={() => setNoticeOpen((value) => !value)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 text-[hsl(var(--primary))]"><Activity className="h-4 w-4" /></button>{noticeOpen && <div className="absolute right-0 top-11 z-30 w-72 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4 text-xs shadow-xl"><div className="font-bold">System notice</div><p className="mt-2 leading-relaxed text-[hsl(var(--muted-foreground))]">This view uses historical IMD gridded rainfall and deterministic persistence/decay. It is not live radar nowcasting.</p></div>}</div></div>
          </div>
        </header>
        <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 lg:px-9 lg:py-8">
          <section id="dashboard" data-testid="section-dashboard" className="scroll-mt-24">
            <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><div className="eyebrow text-[hsl(var(--primary))]">Live GIS dashboard</div><h2 className="display-font mt-2 max-w-3xl text-3xl font-semibold leading-[1.05] tracking-[-.055em] sm:text-5xl">See water risk move<br /><span className="text-[hsl(var(--primary))]">across Hyderabad.</span></h2><p className="mt-3 max-w-2xl text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">A judge-ready view of the selected forecast horizon, simplified flood surface, drainage context, road exposure, and flood-aware routing.</p></div><div className="flex items-center gap-2"><StatusPill label={systemReady ? 'SYSTEM READY' : 'CHECKING'} tone={systemReady ? 'teal' : 'amber'} testId="status-system" /><StatusPill label={health.data?.status ?? 'API'} tone={health.isError ? 'red' : 'teal'} testId="status-api" /></div></div>
            <div className="mb-4 rounded-xl border border-[#d7c697] bg-[#fff8e8] px-4 py-3 text-xs text-[#725b2d]"><div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#b17c21]" /><p><strong className="font-bold">Prototype boundary.</strong> This prototype uses historical IMD gridded rainfall and a deterministic persistence/decay scenario for 0–3 hour forecasting. Operational Doppler Weather Radar nowcasts and authoritative drainage/hydraulic parameters are future integrations. Flood depths and routes must not be used for emergency navigation or engineering decisions.</p></div></div>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_360px]">
              <div className="panel rounded-2xl p-2 sm:p-3"><LeafletMap data={mapLayers.data} visibility={visibility} routes={routeLines} onRoadSelect={onRoadSelect} /></div>
              <aside className="panel rounded-2xl p-5">
                <div className="flex items-center justify-between"><div><div className="eyebrow text-[#26746d]">Selected surface</div><h3 className="display-font mt-1 text-xl font-semibold">Flood intelligence</h3></div><Waves className="h-5 w-5 text-[#258e8d]" /></div>
                {forecastSummary.data && <div className="mt-5 rounded-xl bg-[#173f47] p-4 text-[#e5f2ed]"><div className="eyebrow text-[#9cc5bc]">Forecast</div><div className="display-font mt-2 text-4xl font-semibold">T+{selectedHorizon}<span className="ml-1 text-sm text-[#9cc5bc]">min</span></div><div className="mt-1 text-[10px] text-[#b6d2cc]">{String(forecastSummary.data.rainfall?.provider ?? 'Historical IMD scenario')}</div></div>}
                <div className="mt-4 space-y-2">{mapLayers.isLoading ? <LoadingPanel label="map layers" /> : mapLayers.isError ? <ErrorPanel label="Map layers" /> : <><StatCard label="Maximum depth" value={`${formatNumber(forecastSummary.data?.horizons.find((item) => item.horizon_minutes === selectedHorizon)?.statistics.maximum_depth_cm)} cm`} hint="selected forecast" tone="amber" /><StatCard label="Road layer" value={visibility.roads ? 'Visible' : 'Hidden'} hint="click a road for details" /><StatCard label="Map grid" value={String(mapLayers.data?.limits?.flood_grid ?? '80×60')} hint="simplified web overlay" /></>}</div>
                <div className="mt-5 border-t border-[hsl(var(--border))] pt-4"><div className="mb-3 text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">Flood risk legend</div><div className="grid grid-cols-2 gap-2">{[0, 1, 2, 3].map((risk) => <div key={risk} className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))]"><span className="h-3 w-3 rounded-sm" style={{ backgroundColor: riskColors[risk] }} />{riskLabel(risk)}</div>)}</div></div>
                {selectedRoad && <div className="mt-5 rounded-xl border border-[#b8d0ca] bg-[#eff7f4] p-4"><div className="eyebrow text-[#26746d]">Selected road</div><div className="mt-1 text-sm font-bold">{String(selectedRoadProperties.name ?? 'Unnamed road')}</div><div className="mt-3 grid grid-cols-2 gap-2 text-[10px]"><span>Forecast depth<br /><b className="text-sm">{formatNumber(selectedRoadProperties.forecast_max_depth_cm)} cm</b></span><span>Risk<br /><b className="text-sm">{riskLabel(Number(selectedRoadProperties.forecast_risk_class ?? 0))}</b></span><span>Mean depth<br /><b className="text-sm">{formatNumber(selectedRoadProperties.forecast_mean_depth_cm)} cm</b></span><span>Horizon<br /><b className="text-sm">T+{selectedHorizon}</b></span></div></div>}
                <div className="mt-5 text-[10px] leading-relaxed text-[hsl(var(--muted-foreground))]">Map layers are simplified for browser performance. The original GeoTIFFs and full road graph remain server-side.</div>
              </aside>
            </div>
          </section>

          <section id="forecast" data-testid="section-forecast" className="scroll-mt-24"><SectionHeading eyebrow="01 · Deterministic scenarios" title="Forecast summary" detail="Select a horizon to update the map, summary statistics, road exposure, and routing context without regenerating rasters." action={<StatusPill label={forecastStatus.data?.status ?? 'checking'} tone={forecastStatus.data?.status === 'ready' ? 'teal' : 'amber'} testId="status-forecast" />} /><ForecastSummaryCard query={forecastSummary} selectedHorizon={selectedHorizon} onSelect={setSelectedHorizon} /></section>

          <section id="routing" data-testid="section-routing" className="scroll-mt-24"><SectionHeading eyebrow="02 · Decision support" title="Flood-safe route" detail="Compare a normal shortest route with the existing flood-penalized route at the selected forecast horizon. This is route screening, not emergency navigation." action={<StatusPill label={safeRoute.isError ? 'unavailable' : safeRoute.data ? safeRoute.data.safety : 'ready to query'} tone={safeRoute.isError ? 'red' : safeRoute.data?.safety === 'SAFE' ? 'teal' : 'amber'} testId="status-safe-route" />} /><div className="panel rounded-2xl p-5 sm:p-6"><div className="grid gap-5 lg:grid-cols-[1fr_1.3fr]"><div><div className="flex items-center gap-3"><div className="rounded-xl bg-[#d9efea] p-3 text-[#167269]"><Navigation className="h-5 w-5" /></div><div><div className="text-sm font-bold">Find a flood-aware route</div><div className="text-[10px] text-[hsl(var(--muted-foreground))]">Use decimal latitude / longitude coordinates</div></div></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{[['source_lat', 'Source latitude'], ['source_lon', 'Source longitude'], ['destination_lat', 'Destination latitude'], ['destination_lon', 'Destination longitude']].map(([key, label]) => <label key={key} className="text-[10px] font-bold uppercase tracking-[.08em] text-[hsl(var(--muted-foreground))]">{label}<input value={String(routeParams[key as keyof typeof routeParams])} onChange={(event) => setRouteParams((current) => ({ ...current, [key]: Number(event.target.value) }))} type="number" step="any" className="mt-1 w-full rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.6)] px-3 py-2.5 text-xs font-medium outline-none focus:border-[#258e8d]" /></label>)}</div><div className="mt-3"><div className="mb-2 text-[10px] font-bold uppercase tracking-[.08em] text-[hsl(var(--muted-foreground))]">Route horizon</div><div className="grid grid-cols-4 gap-1.5 sm:grid-cols-7">{horizons.map((minutes) => <button key={minutes} onClick={() => setRouteParams((current) => ({ ...current, forecast_minutes: minutes }))} className={`rounded-md border px-1 py-2 text-[10px] font-bold ${routeParams.forecast_minutes === minutes ? 'border-[#258e8d] bg-[#d9efea] text-[#16645f]' : 'border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]'}`}>T+{minutes}</button>)}</div></div><button onClick={() => setRouteRequested(true)} className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-[#1a7174] px-4 py-3 text-xs font-bold text-white shadow-sm hover:bg-[#145e63]"><RouteIcon className="h-4 w-4" /> Find flood-safe route</button>{safeRoute.isLoading && <div className="mt-3 text-xs text-[hsl(var(--muted-foreground))]">Calculating normal and flood-aware routes…</div>}{safeRoute.isError && <div className="mt-3 text-xs text-[#98423d]">Unable to calculate this route. Try coordinates within the Hyderabad road graph.</div>}</div><div>{safeRoute.data ? <RouteResults route={safeRoute.data} /> : <div className="flex h-full min-h-[230px] items-center justify-center rounded-xl border border-dashed border-[#b8d0ca] bg-[#eff7f4] p-6 text-center"><div><RouteIcon className="mx-auto h-7 w-7 text-[#5b9e99]" /><div className="mt-3 text-sm font-bold text-[#356f6b]">Route comparison ready</div><p className="mt-1 max-w-sm text-[11px] leading-relaxed text-[#6d8587]">Enter points and select a horizon to draw both routes on the map and compare exposure, distance, and time.</p></div></div>}</div></div></div></section>

          <section id="sources" data-testid="section-sources" className="scroll-mt-24"><ModelInformation /><div className="mt-4 grid gap-4 lg:grid-cols-2"><div className="panel rounded-2xl p-5"><SectionHeading eyebrow="03 · Source validation" title="Data status" detail="Read-only checks against the configured Hyderabad inputs." /><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{[['Found', dataStatus.data?.summary.found], ['Readable', dataStatus.data?.summary.readable], ['Valid', dataStatus.data?.summary.valid], ['Missing', dataStatus.data?.summary.missing]].map(([label, value]) => <StatCard key={String(label)} label={String(label)} value={String(value ?? '—')} hint={`of ${dataStatus.data?.summary.total ?? '—'} datasets`} tone={label === 'Missing' && Number(value) > 0 ? 'amber' : 'teal'} />)}</div></div><div className="panel rounded-2xl p-5"><SectionHeading eyebrow="04 · Preparation" title="Model-ready inputs" detail="The existing Step 1–6 preparation remains intact." /><div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{['DEM', 'Land cover', 'Rainfall', 'Nalas', 'Streams', 'Tanks'].map((item) => <div key={item} className="flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.5)] p-3 text-xs font-semibold"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#d9efea] text-[#23756d]"><Check className="h-3 w-3" /></span>{item}</div>)}</div><div className="mt-3 text-[10px] text-[hsl(var(--muted-foreground))]">{preprocessing.data?.available_processed_datasets?.length ?? 0} generated outputs · {preprocessing.data?.warnings?.length ?? 0} warnings</div></div></div></section>

          <footer className="flex flex-col justify-between gap-3 border-t border-[hsl(var(--border))] pb-8 pt-5 text-[10px] text-[hsl(var(--muted-foreground))] sm:flex-row"><span>Prototype estimates only · historical IMD rainfall · no live radar · no emergency navigation</span><span className="mono-font">HYD / UFR / STEP-8</span></footer>
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