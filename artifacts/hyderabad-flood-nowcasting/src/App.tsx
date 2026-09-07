import { useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { LeafletMap } from '@/components/leaflet-map';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Check,
  ChevronDown,
  Database,
  CircleDot,
  CloudRain,
  Droplets,
  FileCheck2,
  FileWarning,
  Gauge,
  GitBranch,
  Layers3,
  MapPinned,
  Menu,
  Navigation,
  RefreshCw,
  Route as RouteIcon,
  ShieldCheck,
  SlidersHorizontal,
  Waves,
  X,
} from 'lucide-react';
import {
  getGetFloodDepthQueryKey,
  getGetForecastQueryKey,
  getGetDataStatusQueryKey,
  getGetHealthQueryKey,
  getGetSafeRouteQueryKey,
  getGetSystemStatusQueryKey,
  getHealthCheckQueryKey,
  useGetFloodDepth,
  useGetForecast,
  useGetDataStatus,
  useGetHealth,
  useGetSafeRoute,
  useGetSystemStatus,
  useHealthCheck,
} from '@workspace/api-client-react';
import type { DatasetStatus, DataStatusSummary } from '@workspace/api-client-react';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';

const queryClient = new QueryClient();

type QueryState = {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
};

function StatusPill({ label, tone = 'teal', testId }: { label: string; tone?: 'teal' | 'amber' | 'red' | 'slate'; testId: string }) {
  const tones = {
    teal: 'bg-[#d9efea] text-[#16645f]',
    amber: 'bg-[#fff0d1] text-[#8c5b16]',
    red: 'bg-[#f8dedb] text-[#98423d]',
    slate: 'bg-[#e3eaeb] text-[#50666b]',
  };
  return <span data-testid={testId} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.1em] ${tones[tone]}`}><span className={`h-1.5 w-1.5 rounded-full ${tone === 'teal' ? 'bg-[#218c83]' : tone === 'amber' ? 'bg-[#c78b2e]' : tone === 'red' ? 'bg-[#b94c46]' : 'bg-[#718589]'}`} />{label}</span>;
}

function QueryStateRow({ query, label }: { query: QueryState; label: string }) {
  if (query.isLoading) return <div data-testid={`loading-${label}`} className="flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]"><span className="skeleton h-2 w-20 rounded-full" /> updating {label}</div>;
  if (query.isError) return <div data-testid={`error-${label}`} className="flex items-center gap-2 text-xs text-[#a34a43]"><AlertTriangle className="h-3.5 w-3.5" /> {label} unavailable · foundation API</div>;
  return null;
}

function SectionHeader({ eyebrow, title, detail, action }: { eyebrow: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <div className="eyebrow text-[hsl(var(--primary))]">{eyebrow}</div>
        <h2 className="display-font mt-1 text-xl font-semibold tracking-[-.03em] text-[hsl(var(--foreground))]">{title}</h2>
        {detail && <p className="mt-1 text-xs leading-relaxed text-[hsl(var(--muted-foreground))]">{detail}</p>}
      </div>
      {action}
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, suffix, hint, tone = 'teal', testId }: {
  icon: typeof Activity; label: string; value: string; suffix?: string; hint: string; tone?: 'teal' | 'amber' | 'red'; testId: string;
}) {
  return (
    <article data-testid={testId} className="panel float-in rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone === 'red' ? 'bg-[#f8dedb] text-[#a14842]' : tone === 'amber' ? 'bg-[#fff0d1] text-[#a36d18]' : 'bg-[#d9efea] text-[#167269]'}`}><Icon className="h-4 w-4" /></div>
        <span className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">SOURCE PENDING</span>
      </div>
      <div className="mt-5 text-[11px] font-semibold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5"><span className="display-font text-[2rem] font-semibold leading-none text-[hsl(var(--foreground))]">{value}</span>{suffix && <span className="mono-font text-xs text-[hsl(var(--muted-foreground))]">{suffix}</span>}</div>
      <div className="mt-2 text-[11px] text-[hsl(var(--muted-foreground))]">{hint}</div>
    </article>
  );
}

function ModelFoundation({ title, message, status, testId }: { title: string; message?: string; status?: string; testId: string }) {
  return (
    <div data-testid={testId} className="rounded-xl border border-dashed border-[#b5cfc9] bg-[#edf6f2] p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-md bg-[#d2e9e2] p-2 text-[#23756d]"><GitBranch className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-bold text-[#225c59]">{title}</span><StatusPill label={status ?? 'not connected'} tone="slate" testId={`${testId}-status`} /></div>
          <p className="mt-1 text-[11px] leading-relaxed text-[#52716e]">{message ?? 'Model endpoint not implemented yet. This panel is a safe foundation for a future estimate.'}</p>
        </div>
      </div>
    </div>
  );
}

type DataStatusView = {
  isLoading: boolean;
  isError: boolean;
  data?: {
    generated_at: string;
    datasets: Record<string, DatasetStatus>;
    summary: DataStatusSummary;
  };
};

function readableDatasetName(value: string) {
  return value.replaceAll('_', ' ');
}

function DatasetStatusSection({ query }: { query: DataStatusView }) {
  const items = Object.values(query.data?.datasets ?? {});
  const statusTone = (status: DatasetStatus['validation_status']) => {
    if (status === 'valid') return 'teal' as const;
    if (status === 'missing') return 'amber' as const;
    return 'red' as const;
  };

  return (
    <section id="data-status" data-testid="section-data-status" className="scroll-mt-24">
      <SectionHeader
        eyebrow="02 · Source validation"
        title="Data status"
        detail="Read-only checks against the configured Hyderabad source files. Missing files are reported, never replaced."
        action={<StatusPill label={query.isError ? 'validation error' : 'read-only'} tone={query.isError ? 'red' : 'slate'} testId="status-data-validation" />}
      />
      {query.isLoading && (
        <div className="panel rounded-xl p-5 text-xs text-[hsl(var(--muted-foreground))]">
          Checking configured datasets…
        </div>
      )}
      {query.isError && (
        <div className="panel rounded-xl border-[#e1b4ae] bg-[#fff3f0] p-5 text-xs text-[#98423d]">
          Dataset validation is unavailable. Check the backend logs before treating any source as ready.
        </div>
      )}
      {query.data && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-4">
            {[
              ['Found', query.data.summary.found, query.data.summary.total],
              ['Readable', query.data.summary.readable, query.data.summary.total],
              ['Valid', query.data.summary.valid, query.data.summary.total],
              ['Missing', query.data.summary.missing, query.data.summary.total],
            ].map(([label, value, total]) => (
              <div key={label} className="panel rounded-xl p-4">
                <div className="text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">{label}</div>
                <div className="display-font mt-1 text-2xl font-semibold">{value}<span className="ml-1 text-sm text-[hsl(var(--muted-foreground))]">/ {total}</span></div>
              </div>
            ))}
          </div>
          <div className="panel rounded-xl p-3 sm:p-4">
            <div className="mb-2 hidden grid-cols-[1.5fr_.65fr_.8fr_1fr] gap-3 px-3 text-[10px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))] sm:grid">
              <span>Dataset</span><span>Type</span><span>Found / readable</span><span>Validation</span>
            </div>
            <div className="space-y-2">
              {items.map((item) => (
                <div key={item.dataset_key} className="grid gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.5)] px-3 py-3 sm:grid-cols-[1.5fr_.65fr_.8fr_1fr] sm:items-center">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-xs font-bold">
                      {item.exists && item.readable ? <FileCheck2 className="h-3.5 w-3.5 text-[#23756d]" /> : <FileWarning className="h-3.5 w-3.5 text-[#b17c21]" />}
                      <span className="truncate">{readableDatasetName(item.dataset_key)}</span>
                    </div>
                    <div className="mt-1 truncate font-mono text-[9px] text-[hsl(var(--muted-foreground))]" title={item.path}>{item.path}</div>
                  </div>
                  <div className="text-[10px] font-bold uppercase tracking-[.08em] text-[hsl(var(--muted-foreground))]">{item.dataset_type}</div>
                  <div className="text-[10px] text-[hsl(var(--muted-foreground))]">{item.exists ? 'found' : 'missing'} · {item.readable ? 'readable' : 'not readable'}</div>
                  <div><StatusPill label={item.validation_status} tone={statusTone(item.validation_status)} testId={`status-dataset-${item.dataset_key}`} /></div>
                </div>
              ))}
            </div>
            <div className="mt-3 text-right text-[10px] text-[hsl(var(--muted-foreground))]">
              Checked {new Date(query.data.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function RainChart() {
  return (
    <div data-testid="chart-rainfall" className="relative mt-2 flex h-44 items-center justify-center rounded-lg bg-[#eff7f4] p-3">
      <div className="chart-grid absolute inset-x-3 inset-y-4 opacity-50" />
      <div className="relative max-w-xs text-center">
        <CloudRain className="mx-auto h-7 w-7 text-[#5b9e99]" />
        <p className="mt-3 text-xs font-bold text-[#356f6b]">Rainfall series pending</p>
        <p className="mt-1 text-[10px] leading-relaxed text-[#6d8587]">Connect a validated IMD or radar source before displaying observations.</p>
      </div>
    </div>
  );
}

function Home() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [lastRefresh, setLastRefresh] = useState('Not synced');
  const [activeNav, setActiveNav] = useState('overview');
  const [noticeOpen, setNoticeOpen] = useState(false);

  const systemStatus = useGetSystemStatus({ query: { queryKey: getGetSystemStatusQueryKey() } });
  const healthCheck = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey() } });
  const dataStatus = useGetDataStatus({ query: { queryKey: getGetDataStatusQueryKey() } });
  const health = useGetHealth({ query: { queryKey: getGetHealthQueryKey() } });
  const forecast = useGetForecast({ query: { queryKey: getGetForecastQueryKey() } });
  const floodDepth = useGetFloodDepth({ query: { queryKey: getGetFloodDepthQueryKey() } });
  const safeRoute = useGetSafeRoute({ query: { queryKey: getGetSafeRouteQueryKey() } });

  const refreshAll = async () => {
    await Promise.all([systemStatus.refetch(), healthCheck.refetch(), dataStatus.refetch(), health.refetch(), forecast.refetch(), floodDepth.refetch(), safeRoute.refetch()]);
    setLastRefresh(new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }).format(new Date()) + ' IST');
  };

  const scrollTo = (target: string) => {
    setActiveNav(target);
    setMobileNavOpen(false);
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  const systemTone = systemStatus.data?.status?.toLowerCase().includes('ok') ? 'teal' : systemStatus.isError ? 'amber' : 'teal';
  const systemLabel = systemStatus.data?.status ?? 'Operational';

  const navItems = [
    { id: 'overview', label: 'Current status', icon: Activity },
    { id: 'rainfall', label: 'Rainfall context', icon: CloudRain },
    { id: 'data-status', label: 'Data status', icon: Database },
    { id: 'forecast', label: 'Flood forecast', icon: BarChart3 },
    { id: 'depth', label: 'Flood depth', icon: Waves },
    { id: 'drainage', label: 'Drainage network', icon: GitBranch },
    { id: 'safe-route', label: 'Safe route', icon: RouteIcon },
  ];

  return (
    <div className="app-shell min-h-[100dvh]">
      <aside className={`sidebar-grid fixed inset-y-0 left-0 z-40 w-[250px] bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] transition-transform duration-300 md:translate-x-0 ${mobileNavOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex h-full flex-col">
          <div className="flex items-start justify-between border-b border-[hsl(var(--sidebar-border))] px-5 py-5">
            <button data-testid="button-brand" onClick={() => scrollTo('overview')} className="text-left">
              <div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[hsl(var(--sidebar-primary))] text-[#173d42]"><Droplets className="h-4 w-4" /></span><span className="display-font text-sm font-bold tracking-[-.02em]">HYD · NOWCAST</span></div>
              <p className="mt-3 pl-10 text-[9px] uppercase tracking-[.16em] text-[#a7c4c2]">Urban resilience desk</p>
            </button>
            <button data-testid="button-close-navigation" onClick={() => setMobileNavOpen(false)} className="rounded-md p-1 text-[#b0ccca] hover:bg-[hsl(var(--sidebar-accent))] md:hidden"><X className="h-4 w-4" /></button>
          </div>
          <div className="px-3 py-5">
            <div className="eyebrow px-3 pb-2 text-[#88aaa8]">Command view</div>
            <nav className="space-y-1">
              {navItems.map(({ id, label, icon: Icon }) => <button data-testid={`nav-${id}`} key={id} onClick={() => scrollTo(id)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs font-semibold transition-colors ${activeNav === id ? 'bg-[hsl(var(--sidebar-accent))] text-[#f0d38b]' : 'text-[#b5ccca] hover:bg-[hsl(var(--sidebar-accent))] hover:text-white'}`}><Icon className="h-4 w-4" /><span>{label}</span>{id === 'overview' && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#f1c263]" />}</button>)}
            </nav>
          </div>
          <div className="mt-auto border-t border-[hsl(var(--sidebar-border))] p-4">
            <div className="rounded-lg border border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-accent)/.55)] p-3">
              <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.12em] text-[#a6c5c2]"><ShieldCheck className="h-3.5 w-3.5 text-[#f0c96d]" /> Trust boundary</div>
              <p className="mt-2 text-[10px] leading-relaxed text-[#91b2b0]">Context and prototype signals only. Not an engineering-grade warning.</p>
            </div>
            <div className="mt-4 flex items-center justify-between text-[10px] text-[#7e9f9e]"><span>Foundation v0.1</span><span className="mono-font">HYD-01</span></div>
          </div>
        </div>
      </aside>
      {mobileNavOpen && <button aria-label="Close navigation" data-testid="button-navigation-overlay" onClick={() => setMobileNavOpen(false)} className="fixed inset-0 z-30 bg-[#113841]/30 md:hidden" />}

      <main className="min-h-[100dvh] md:pl-[250px]">
        <header className="sticky top-0 z-20 border-b border-[hsl(var(--border)/.8)] bg-[hsl(var(--background)/.88)] px-4 py-3 backdrop-blur-xl sm:px-6 lg:px-9">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <button data-testid="button-open-navigation" onClick={() => setMobileNavOpen(true)} className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 md:hidden"><Menu className="h-4 w-4" /></button>
              <div><div className="eyebrow text-[hsl(var(--muted-foreground))]">Monsoon operations · 18 Jun 2025</div><h1 className="display-font mt-0.5 text-lg font-semibold tracking-[-.03em]">Hyderabad situation room</h1></div>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <div className="hidden text-right sm:block"><div className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">LAST SYNC</div><div data-testid="text-last-refresh" className="mono-font mt-0.5 text-xs text-[hsl(var(--foreground))]">{lastRefresh}</div></div>
              <button data-testid="button-refresh-data" onClick={refreshAll} className="flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))] shadow-sm transition-transform hover:-translate-y-0.5 active:translate-y-0"><RefreshCw className={`h-3.5 w-3.5 ${[systemStatus, healthCheck, dataStatus, health, forecast, floodDepth, safeRoute].some((query) => query.isFetching) ? 'animate-spin' : ''}`} /><span className="hidden sm:inline">Refresh</span></button>
              <div className="relative">
                <button data-testid="button-notifications" onClick={() => setNoticeOpen((open) => !open)} className="relative rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2 text-[hsl(var(--primary))] shadow-sm"><Bell className="h-4 w-4" /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[#c4534d]" /></button>
                {noticeOpen && <div data-testid="panel-notifications" className="absolute right-0 top-11 z-30 w-64 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-3 shadow-lg"><div className="flex items-center justify-between"><span className="text-xs font-bold">Operational notices</span><button data-testid="button-close-notifications" onClick={() => setNoticeOpen(false)} className="rounded p-1 text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]"><X className="h-3.5 w-3.5" /></button></div><p className="mt-2 text-[11px] leading-relaxed text-[hsl(var(--muted-foreground))]">No new notices. Continue monitoring the rainfall context and field reports.</p></div>}
              </div>
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-[1500px] space-y-8 px-4 py-6 sm:px-6 lg:px-9 lg:py-8">
          <section id="overview" data-testid="section-current-status" className="scroll-mt-24">
            <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
              <div><div className="eyebrow text-[hsl(var(--primary))]">Current status</div><h2 className="display-font mt-2 max-w-2xl text-3xl font-semibold leading-[1.05] tracking-[-.055em] sm:text-4xl">A clear read on<br /><span className="text-[hsl(var(--primary))]">water in motion.</span></h2><p className="mt-3 max-w-xl text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">A shared operational picture for Hyderabad teams. Read the rainfall context first, then use the model foundations as they come online.</p></div>
              <div className="flex flex-wrap items-center gap-2"><StatusPill label={systemLabel} tone={systemTone} testId="status-system" /><StatusPill label={health.data?.status ?? 'API connected'} tone={health.isError ? 'amber' : 'teal'} testId="status-api" /></div>
            </div>
            <div className="mb-4 rounded-xl border border-[#d7c697] bg-[#fff8e8] px-4 py-3 text-xs text-[#725b2d]"><div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#b17c21]" /><p><strong className="font-bold">Use with judgement.</strong> This prototype provides city-scale context, not street-level certainty. Confirm conditions with field teams before acting.</p></div></div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard icon={CloudRain} label="Rainfall · city average" value="—" hint="Awaiting validated rainfall input" testId="metric-rainfall" />
              <MetricCard icon={Gauge} label="Peak intensity" value="—" hint="No intensity source connected" tone="amber" testId="metric-intensity" />
              <MetricCard icon={Waves} label="River gauge · Musi" value="—" hint="No gauge data connected" tone="amber" testId="metric-river" />
              <MetricCard icon={ShieldCheck} label="Operational posture" value="Prototype" hint="No flood alert is issued" tone="red" testId="metric-posture" />
            </div>
          </section>

          <section id="rainfall" data-testid="section-rainfall" className="scroll-mt-24">
            <SectionHeader eyebrow="01 · Rainfall" title="Rainfall context" detail="Observed pattern across the urban extent, kept deliberately separate from model estimates." action={<button data-testid="button-rainfall-layer" onClick={() => scrollTo('rainfall')} className="hidden items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))] sm:flex"><Layers3 className="h-3.5 w-3.5" /> Layer: observed</button>} />
            <div className="grid gap-4 xl:grid-cols-[1.45fr_1fr]">
              <div className="panel rounded-xl p-5"><div className="flex items-center justify-between"><div><div className="text-xs font-bold">Catchment pulse</div><div className="mt-1 text-[11px] text-[hsl(var(--muted-foreground))]">Source slots for future ingestion</div></div><CloudRain className="h-5 w-5 text-[hsl(var(--primary))]" /></div><div className="mt-5 space-y-3">
                {['Musi upper catchment', 'Hussainsagar basin', 'Himayat Sagar basin'].map((name) => <div key={name} className="rounded-lg border border-dashed border-[#b8d0ca] bg-[#f4faf7] px-3 py-3"><div className="flex justify-between text-xs"><span className="font-semibold">{name}</span><span className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">NO DATA</span></div><div className="mt-2 h-1.5 rounded-full bg-[#dfebe8]" /><div className="mt-1 text-[10px] text-[hsl(var(--muted-foreground))]">Awaiting validated rainfall source</div></div>)}
              </div></div>
            </div>
          </section>

          <DatasetStatusSection query={dataStatus} />

          <section className="grid gap-4 xl:grid-cols-[1.3fr_.7fr]">
            <div id="forecast" data-testid="section-flood-forecast" className="panel scroll-mt-24 rounded-xl p-5 sm:p-6">
              <SectionHeader eyebrow="02 · Model foundation" title="Flood forecast" detail="Horizon and model connection status, not an issued forecast." action={<StatusPill label={forecast.isError ? 'offline' : 'foundation'} tone={forecast.isError ? 'amber' : 'slate'} testId="status-forecast-model" />} />
              <div className="grid gap-5 md:grid-cols-[1fr_1.2fr]">
                <div className="rounded-xl bg-[#173f47] p-5 text-[#e5f2ed]"><div className="eyebrow text-[#9cc5bc]">Supported horizon</div><div className="display-font mt-3 text-5xl font-semibold tracking-[-.06em]">{systemStatus.data?.forecast_horizon_hours ?? '—'}<span className="ml-2 text-lg font-medium text-[#9cc5bc]">hours</span></div><div className="mt-3 flex items-center gap-2 text-xs text-[#b6d2cc]"><CircleDot className="h-3.5 w-3.5 text-[#f1c263]" /> prototype horizon declared by API</div></div>
                <div><div className="mb-3 flex items-center justify-between"><span className="text-xs font-bold">Forecast readiness</span><span className="mono-font text-[10px] text-[hsl(var(--muted-foreground))]">0 / 3 layers</span></div><div className="space-y-2">{['Rainfall ingestion', 'Terrain + drainage model', 'Flood probability surface'].map((item) => <div key={item} className="flex items-center gap-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background)/.55)] px-3 py-2.5"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#d9efea] text-[#26776f]"><Check className="h-3 w-3" /></span><span className="text-xs">{item}</span><span className="ml-auto text-[9px] font-bold uppercase tracking-[.1em] text-[hsl(var(--muted-foreground))]">planned</span></div>)}</div><div className="mt-4"><QueryStateRow query={forecast} label="forecast endpoint" /></div></div>
              </div>
              <div className="mt-5"><ModelFoundation title="No live flood estimate" message={forecast.data?.message ?? 'The forecast endpoint is present for integration, but model output is not implemented yet. Do not interpret this view as a warning.'} status={forecast.data?.status} testId="placeholder-forecast" /></div>
            </div>
            <div id="depth" data-testid="section-flood-depth" className="panel scroll-mt-24 rounded-xl p-5 sm:p-6">
              <SectionHeader eyebrow="03 · Model foundation" title="Flood depth" detail="A future depth surface for triage and context." />
              <div className="relative mt-5 flex min-h-[190px] items-center justify-center overflow-hidden rounded-xl border border-[#b6d5cf] bg-[#dcefe9]"><div className="absolute inset-0 opacity-50" style={{ backgroundImage: 'radial-gradient(circle at 35% 35%, #4da29b 0 2px, transparent 3px), radial-gradient(circle at 68% 63%, #337f80 0 2px, transparent 3px)', backgroundSize: '24px 24px' }} /><div className="relative text-center"><div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-[#eff8f4] text-[#287c76] shadow-sm"><Waves className="h-5 w-5" /></div><div className="mt-3 text-sm font-bold text-[#23655f]">Depth surface pending</div><div className="mt-1 text-[10px] text-[#4f7c77]">No spatial values returned by the model</div></div><div className="absolute bottom-3 left-3 rounded bg-[#eff8f4]/85 px-2 py-1 text-[9px] uppercase tracking-[.1em] text-[#42736e]">0.0 m · unavailable</div></div><div className="mt-4"><ModelFoundation title="Depth model endpoint" message={floodDepth.data?.message} status={floodDepth.data?.status} testId="placeholder-depth" /></div></div>
          </section>

          <section id="drainage" data-testid="section-drainage" className="scroll-mt-24">
            <SectionHeader eyebrow="04 · Infrastructure context" title="Drainage network" detail="A geographic reference layer for teams to orient around known conveyance corridors." action={<button data-testid="button-filter-drainage" onClick={() => scrollTo('drainage')} className="flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 text-xs font-bold text-[hsl(var(--primary))]"><SlidersHorizontal className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Filter layer</span><ChevronDown className="h-3 w-3" /></button>} />
            <div className="panel map-panel overflow-hidden rounded-xl p-2 sm:p-3"><div className="grid h-full gap-3 lg:grid-cols-[1fr_260px]"><LeafletMap /><div className="flex flex-col rounded-lg bg-[#eff7f4] p-4"><div className="eyebrow text-[#26746d]">Layer legend</div><div className="mt-4 space-y-3 text-xs">{[['#258e8d', 'Primary drain / nala'], ['#7ba9a5', 'Urban river corridor'], ['#c4534d', 'Rain cell · indicative'], ['#d19a38', 'Catchment attention']].map(([color, label]) => <div key={label} className="flex items-center gap-2.5"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} /><span className="text-[#456765]">{label}</span></div>)}</div><div className="mt-auto border-t border-[#cfe2dc] pt-4"><div className="flex items-center gap-2 text-xs font-bold text-[#356763]"><MapPinned className="h-4 w-4" /> Geographic context</div><p className="mt-2 text-[10px] leading-relaxed text-[#668682]">Map layers are illustrative. Verify asset condition and access on the ground.</p></div></div></div></div>
          </section>

          <section id="safe-route" data-testid="section-safe-route" className="scroll-mt-24">
            <SectionHeader eyebrow="05 · Decision support" title="Safe route" detail="A future route recommendation layer. No route should be treated as safe from this prototype." action={<StatusPill label={safeRoute.isError ? 'endpoint unavailable' : 'not operational'} tone="amber" testId="status-safe-route" />} />
            <div className="panel rounded-xl p-5 sm:p-6"><div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]"><div className="flex items-start gap-4"><div className="rounded-xl bg-[#fff0d1] p-3 text-[#a16f22]"><Navigation className="h-5 w-5" /></div><div><h3 className="display-font text-base font-semibold">Route guidance is not active</h3><p className="mt-2 max-w-md text-xs leading-relaxed text-[hsl(var(--muted-foreground))]">The system is not yet connected to road closures, live depth, or emergency access constraints. Keep this module visible so the boundary stays clear.</p></div></div><div><ModelFoundation title="Safe route endpoint" message={safeRoute.data?.message ?? 'Route generation is planned. Connect validated road and hazard data before publishing guidance.'} status={safeRoute.data?.status} testId="placeholder-safe-route" /><div className="mt-4 flex flex-wrap gap-2"><button data-testid="button-route-layer" disabled className="cursor-not-allowed rounded-lg bg-[#d9e5e2] px-3 py-2 text-xs font-bold text-[#78908c]">Select origin</button><button data-testid="button-destination-layer" disabled className="cursor-not-allowed rounded-lg bg-[#d9e5e2] px-3 py-2 text-xs font-bold text-[#78908c]">Select destination</button></div></div></div></div>
          </section>

          <footer className="flex flex-col justify-between gap-3 border-t border-[hsl(var(--border))] pb-8 pt-5 text-[10px] text-[hsl(var(--muted-foreground))] sm:flex-row"><div className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-[#d19a38] status-pulse" /> <span data-testid="text-footer-disclaimer">Prototype foundation · model endpoints are not implemented</span></div><div className="flex gap-4"><span>Data posture: contextual</span><span className="mono-font">HYD / UFR / 0.1</span></div></footer>
        </div>
      </main>
    </div>
  );
}

function Router() {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={Home} />
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
