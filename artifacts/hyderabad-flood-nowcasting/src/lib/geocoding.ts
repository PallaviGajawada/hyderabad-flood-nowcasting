export type PlaceSearchResult = {
  id: string;
  label: string;
  secondaryLabel: string;
  lat: number;
  lon: number;
  source: 'Hyderabad places' | 'OpenStreetMap';
};

const knownPlaces: Array<Omit<PlaceSearchResult, 'source'> & { aliases?: string[] }> = [
  { id: 'secunderabad', label: 'Secunderabad', secondaryLabel: 'Secunderabad, Hyderabad', lat: 17.4399, lon: 78.4983 },
  { id: 'hitech-city', label: 'HITEC City', secondaryLabel: 'Hitech City · Madhapur, Hyderabad', aliases: ['Hitech City', 'Hi Tech City'], lat: 17.4435, lon: 78.3772 },
  { id: 'charminar', label: 'Charminar', secondaryLabel: 'Old City, Hyderabad', lat: 17.3616, lon: 78.4747 },
  { id: 'gachibowli', label: 'Gachibowli', secondaryLabel: 'West Hyderabad', lat: 17.4401, lon: 78.3489 },
  { id: 'lb-nagar', label: 'LB Nagar', secondaryLabel: 'East Hyderabad', aliases: ['L B Nagar', 'LB nagar'], lat: 17.3457, lon: 78.5522 },
  { id: 'kukatpally', label: 'Kukatpally', secondaryLabel: 'North-west Hyderabad', lat: 17.4849, lon: 78.4138 },
  { id: 'madhapur', label: 'Madhapur', secondaryLabel: 'West Hyderabad', lat: 17.4483, lon: 78.3915 },
];

function normalize(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

export async function searchHyderabadPlaces(query: string, signal?: AbortSignal): Promise<PlaceSearchResult[]> {
  const cleanQuery = query.trim();
  if (cleanQuery.length < 2) return [];

  const normalizedQuery = normalize(cleanQuery);
  const localMatches = knownPlaces
    .filter((place) => [place.label, place.secondaryLabel, ...(place.aliases ?? [])]
      .some((value) => normalize(value).includes(normalizedQuery)))
    .map(({ aliases: _aliases, ...place }) => ({ ...place, source: 'Hyderabad places' as const }));

  if (localMatches.length > 0) return localMatches;

  const response = await fetch(
    `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&addressdetails=1&accept-language=en&q=${encodeURIComponent(`${cleanQuery}, Hyderabad, Telangana, India`)}`,
    { signal, headers: { Accept: 'application/json' } },
  );
  if (!response.ok) throw new Error('Place search is unavailable right now.');

  const results = (await response.json()) as Array<{
    place_id?: number;
    display_name?: string;
    lat?: string;
    lon?: string;
    type?: string;
  }>;

  return results
    .map((result) => ({
      id: `osm-${result.place_id ?? result.display_name ?? result.lat}`,
      label: String(result.display_name ?? cleanQuery).split(',')[0],
      secondaryLabel: String(result.display_name ?? 'OpenStreetMap result')
        .split(',')
        .slice(1, 4)
        .join(',')
        .trim(),
      lat: Number(result.lat),
      lon: Number(result.lon),
      source: 'OpenStreetMap' as const,
    }))
    .filter((result) => Number.isFinite(result.lat) && Number.isFinite(result.lon));
}