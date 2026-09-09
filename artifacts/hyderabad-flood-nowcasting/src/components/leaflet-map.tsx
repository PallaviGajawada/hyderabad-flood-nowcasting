import { useEffect, useRef, useState } from 'react';
import type { MapLayersResponse, RoutePoint } from '@workspace/api-client-react';

type GeoFeature = {
  type?: string;
  geometry?: unknown;
  properties?: Record<string, unknown>;
};

type LayerVisibility = {
  flood: boolean;
  roads: boolean;
  nalas: boolean;
  waterbodies: boolean;
  boundary: boolean;
};

type RouteLine = {
  points: RoutePoint[];
  color: string;
  weight: number;
  dashArray?: string;
};

declare global {
  interface Window {
    L?: any;
  }
}

const riskColors: Record<number, string> = {
  0: '#9ec9c2',
  1: '#f0c96d',
  2: '#e5944f',
  3: '#cf5d50',
  4: '#8f2d35',
};

function featureId(feature: GeoFeature, index: number) {
  const properties = feature.properties ?? {};
  return String(properties.osmid ?? properties.Nala_ID ?? properties.name ?? index);
}

export function LeafletMap({
  data,
  visibility,
  routes = [],
  onRoadSelect,
}: {
  data?: MapLayersResponse;
  visibility: LayerVisibility;
  routes?: RouteLine[];
  onRoadSelect: (feature: GeoFeature | null) => void;
}) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<any>(null);
  const overlayLayer = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!mapRef.current || !window.L) return;
    const leaflet = window.L;
    const map = leaflet.map(mapRef.current, { zoomControl: false, preferCanvas: true });
    leaflet.control.zoom({ position: 'bottomright' }).addTo(map);
    map.setView([17.4065, 78.4772], 11);
    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18,
    }).addTo(map);
    mapInstance.current = map;
    setMapReady(true);
    window.setTimeout(() => map.invalidateSize(), 100);
    return () => {
      overlayLayer.current = null;
      mapInstance.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapInstance.current;
    const leaflet = window.L;
    if (!map || !leaflet || !data) return;
    overlayLayer.current?.clearLayers();
    const overlays = leaflet.layerGroup().addTo(map);
    overlayLayer.current = overlays;

    const collection = (name: string) => data.layers?.[name] as any;
    if (visibility.flood && collection('flood')) {
      leaflet.geoJSON(collection('flood'), {
        style: (feature: GeoFeature) => ({
          color: riskColors[Number(feature.properties?.risk_class ?? 0)] ?? riskColors[0],
          weight: 0,
          fillColor: riskColors[Number(feature.properties?.risk_class ?? 0)] ?? riskColors[0],
          fillOpacity: 0.47,
        }),
        onEachFeature: (feature: GeoFeature, layer: any) => {
          layer.bindTooltip(
            `${Number(feature.properties?.depth_cm ?? 0).toFixed(1)} cm · risk class ${feature.properties?.risk_class ?? 0}`,
            { sticky: true },
          );
        },
      }).addTo(overlays);
    }
    if (visibility.boundary && collection('boundary')) {
      leaflet.geoJSON(collection('boundary'), {
        style: { color: '#176f76', weight: 2, dashArray: '5 5', fillOpacity: 0 },
      }).addTo(overlays);
    }
    if (visibility.waterbodies && collection('waterbodies')) {
      leaflet.geoJSON(collection('waterbodies'), {
        style: { color: '#4d9ca0', weight: 1, fillColor: '#78c3be', fillOpacity: 0.23 },
      }).addTo(overlays);
    }
    if (visibility.nalas && collection('nalas')) {
      leaflet.geoJSON(collection('nalas'), {
        style: { color: '#2c8e8b', weight: 2.4, opacity: 0.84 },
        onEachFeature: (feature: GeoFeature, layer: any) => {
          layer.bindTooltip(String(feature.properties?.Nala_Name ?? 'Nala'), { sticky: true });
        },
      }).addTo(overlays);
    }
    if (visibility.roads && collection('road_risk')) {
      leaflet.geoJSON(collection('road_risk'), {
        style: (feature: GeoFeature) => {
          const risk = Number(feature.properties?.prototype_max_risk_class ?? 0);
          return {
            color: riskColors[risk] ?? '#527478',
            weight: risk >= 2 ? 2.2 : 1.1,
            opacity: risk >= 2 ? 0.85 : 0.55,
          };
        },
        onEachFeature: (feature: GeoFeature, layer: any) => {
          layer.on('click', () => onRoadSelect(feature));
          layer.bindTooltip(String(feature.properties?.name ?? 'Unnamed road'), { sticky: true });
        },
      }).addTo(overlays);
    }
    routes.forEach((route) => {
      leaflet.polyline(
        route.points.map((point) => [point.lat, point.lon]),
        {
          color: route.color,
          weight: route.weight,
          opacity: 0.92,
          dashArray: route.dashArray,
        },
      ).addTo(overlays);
    });
    window.setTimeout(() => map.invalidateSize(), 50);
  }, [data, visibility, routes, onRoadSelect]);

  return (
    <div data-testid="map-hyderabad" className="relative h-full min-h-[510px] overflow-hidden rounded-xl border border-[hsl(var(--border))] bg-[#d9e7e2]">
      <div ref={mapRef} className={`leaflet-map absolute inset-0 ${mapReady ? 'block' : 'hidden'}`} />
      {!mapReady && (
        <div className="map-fallback absolute inset-0">
          <svg viewBox="0 0 800 500" className="absolute inset-0 h-full w-full opacity-80" aria-hidden="true">
            <path d="M340 0 C280 120 430 175 350 270 C290 340 410 380 350 500" fill="none" stroke="#70a7a7" strokeWidth="8" opacity=".7" />
            <path d="M50 180 L720 275 M170 40 L560 450 M630 30 L250 460 M40 390 L750 120" stroke="#91b6b3" strokeWidth="3" opacity=".65" />
            <path d="M160 220 L270 180 L360 220 L450 170 L570 230 L520 330 L380 350 L260 310 Z" fill="#65aaa0" fillOpacity=".16" stroke="#197e82" strokeWidth="3" strokeDasharray="8 7" />
          </svg>
          <div className="absolute inset-x-4 bottom-4 rounded-lg border border-[#b8d0ca] bg-[#eff7f3]/90 px-3 py-2 text-[10px] font-semibold text-[#315c5c] backdrop-blur-sm">
            Loading Hyderabad base map and cached web layers…
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card)/.92)] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[.12em] text-[hsl(var(--primary))] shadow-sm">
        Hyderabad · interactive GIS
      </div>
      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-[hsl(var(--card)/.94)] px-2.5 py-1.5 text-[10px] text-[hsl(var(--muted-foreground))] shadow-sm">
        {data ? `${data.limits?.flood_grid ?? '80x60'} forecast grid · simplified roads` : 'Loading map layers'}
      </div>
      <div className="pointer-events-none absolute bottom-3 right-3 flex items-center gap-2 rounded-md bg-[hsl(var(--card)/.94)] px-2.5 py-1.5 text-[10px] text-[hsl(var(--muted-foreground))] shadow-sm">
        <span className="h-2 w-2 rounded-full bg-[#cf5d50]" /> Depth / risk
      </div>
    </div>
  );
}

export type { GeoFeature, LayerVisibility, RouteLine };