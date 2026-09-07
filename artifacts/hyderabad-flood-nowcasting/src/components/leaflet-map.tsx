import { useEffect, useRef, useState } from 'react';

declare global {
  interface Window {
    L?: {
      map: (element: HTMLElement, options?: Record<string, unknown>) => LeafletMap;
      tileLayer: (url: string, options?: Record<string, unknown>) => {
        addTo: (map: LeafletMap) => unknown;
      };
      circleMarker: (coordinates: [number, number], options?: Record<string, unknown>) => {
        addTo: (map: LeafletMap) => {
          bindTooltip: (content: string, options?: Record<string, unknown>) => unknown;
        };
        bindTooltip: (content: string, options?: Record<string, unknown>) => unknown;
      };
      polygon: (coordinates: Array<[number, number]>, options?: Record<string, unknown>) => {
        addTo: (map: LeafletMap) => unknown;
      };
    };
  }
}

interface LeafletMap {
  setView: (coordinates: [number, number], zoom: number) => unknown;
  remove: () => void;
}

export function LeafletMap() {
  const mapRef = useRef<HTMLDivElement>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!mapRef.current || !window.L) return;
    const leaflet = window.L;
    const map = leaflet.map(mapRef.current, { zoomControl: false });
    map.setView([17.4065, 78.4772], 11);
    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 18,
    }).addTo(map);
    leaflet.polygon([
      [17.52, 78.29], [17.54, 78.56], [17.32, 78.63], [17.29, 78.35],
    ], { color: '#197e82', weight: 1, fillColor: '#42a9a0', fillOpacity: 0.06 }).addTo(map);
    setMapReady(true);
    return () => map.remove();
  }, []);

  return (
    <div data-testid="map-hyderabad" className="relative h-full min-h-[405px] overflow-hidden rounded-xl border border-[hsl(var(--border))] bg-[#d9e7e2]">
      <div ref={mapRef} className={`leaflet-map absolute inset-0 ${mapReady ? 'block' : 'hidden'}`} />
      {!mapReady && (
        <div className="map-fallback absolute inset-0">
          <svg viewBox="0 0 800 500" className="absolute inset-0 h-full w-full opacity-80" aria-hidden="true">
            <path d="M340 0 C280 120 430 175 350 270 C290 340 410 380 350 500" fill="none" stroke="#70a7a7" strokeWidth="8" opacity=".7" />
            <path d="M50 180 L720 275 M170 40 L560 450 M630 30 L250 460 M40 390 L750 120" stroke="#91b6b3" strokeWidth="3" opacity=".65" />
            <path d="M160 220 L270 180 L360 220 L450 170 L570 230 L520 330 L380 350 L260 310 Z" fill="#65aaa0" fillOpacity=".16" stroke="#197e82" strokeWidth="3" strokeDasharray="8 7" />
          </svg>
          <div className="absolute inset-x-4 bottom-4 rounded-lg border border-[#b8d0ca] bg-[#eff7f3]/90 px-3 py-2 text-[10px] font-semibold text-[#315c5c] backdrop-blur-sm">
            Base map loading · illustrative Hyderabad extent
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card)/.9)] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[.12em] text-[hsl(var(--primary))] shadow-sm">
        Hyderabad · urban extent
      </div>
      <div className="pointer-events-none absolute bottom-3 right-3 flex items-center gap-2 rounded-md bg-[hsl(var(--card)/.9)] px-2.5 py-1.5 text-[10px] text-[hsl(var(--muted-foreground))] shadow-sm">
        <span className="h-2 w-2 rounded-full bg-[#258e8d]" /> Context map · illustrative
      </div>
    </div>
  );
}