// Compiled episode IR consumed by the Studio engine.
// Produced by 01_工作流/history-studio/studio.py build; never hand-written.
// All times are absolute seconds; all map coordinates are world pixels of the
// episode projection (see projection below), already resolved from place ids.

export type Span = {start: number; end: number};

export type Place = {
  id: string;
  name: string;
  x: number;
  y: number;
  lon: number;
  lat: number;
  precision: string;
  // 第12批 (2026-10-24): administrative ranks; `city` is the old undifferentiated rank (drawn as a county town)
  tier: 'capital' | 'province' | 'commandery' | 'county' | 'city' | 'stronghold' | 'pass' | 'ferry' | 'region';
};

export type Segment = {
  id: string;
  text: string;
  caption: string;
  start: number;
  end: number;
  voice_onset: number;
  voice_offset: number;
  captions?: {t0: number; t1: number; text: string}[];
  speaker?: string | null;   // a line spoken by the historical figure himself
};

export type CameraKey = {t: number; cx: number; cy: number; z: number};

export type CityEl = Span & {type: 'city'; place: string; detail?: string; dx: number; dy: number; active: [number, number][];
  phases?: {t: number; tier: Place['tier']; seat: boolean}[]};   // rank and ruler badge by story date
// a commander's encampment: tents at a place for as long as the army stays there (2026-10-19)
// a painted scene in a feathered oval over the map (2026-10-20)
export type VignetteEl = Span & {type: 'vignette'; image: string; text?: string | null; pos?: 'center' | 'left' | 'right'; zoom: number};
export type CampEl = Span & {type: 'camp'; place: string; text: string; color: string; offset?: [number, number]; faction?: string; unit?: string; image?: string};
// a faint route left behind by a march (2026-10-19): stays until the same unit moves again
export type TrailEl = Span & {type: 'trail'; points: string[]; color: string; label?: string | null};
export type FlagEl = Span & {type: 'flag'; place: string; name: string; sub?: string; color: string; side: 'left' | 'right'; note?: string; exit_at?: number; turn_at?: number; turn_color?: string; turn_sub?: string; image?: string | null};
export type ArrowEl = Span & {
  type: 'arrow';
  points: string[];
  kind: 'recorded' | 'direction' | 'relation' | 'flee';
  grow: number;
  label?: string;
  stop: 'at' | 'near' | 'approach';
  bend: number;
  color?: string;
  troops?: {kind: 'cavalry' | 'infantry' | 'archer' | 'crossbow'; banner?: string; size: number; rout?: boolean; head_image?: string; head_name?: string};
  // a leader and a pursuer on one road; each is a portrait medallion (2026-10-19)
  chase?: {lag?: number; leader: {src: string; name: string; color: string}; pursuer: {src: string; name: string; color: string}};
};
export type BattleEl = Span & {type: 'battle'; place: string; title?: string; text?: string; side: 'left' | 'right'};
export type CardEl = Span & {type: 'card'; place?: string; title: string; body?: string; side: 'left' | 'right'};
export type PortraitEl = Span & {type: 'portrait'; image: string | null; name: string; title: string; note: string};
export type HeadlineEl = Span & {type: 'headline'; text: string; sub?: string};
export type RegionEl = Span & {type: 'region'; region: string; label?: string};
export type StampEl = Span & {type: 'stamp'; place: string; text: string};
export type PersonColor = {fill: string; edge: string; flag: string};
// faces: which way the painted face looks; a figure is mirrored so it looks into the frame (left side → right, right side → left)
type PersonBase = {who: string; name: string; title: string; role: string; faction: string | null; color: PersonColor; image: string | null; cutout?: boolean; place: string | null; side: 'left' | 'right'; faces?: 'left' | 'right' | 'front'};
export type EnterEl = Span & PersonBase & {type: 'enter'; note?: string | null; settle?: boolean};
export type PersonCardEl = Span & PersonBase & {type: 'person_card'; base?: string | null};
export type ExitEl = Span & PersonBase & {type: 'exit'; verb: string; show_portrait: boolean};
export type VersusSide = {who: string; name: string; title: string; image: string | null; cutout?: boolean; color: PersonColor; faces?: 'left' | 'right' | 'front'};
export type VersusEl = Span & {type: 'versus'; left: VersusSide; right: VersusSide; label: string; caption?: string | null};
export type TitleBarEl = Span & {type: 'title_bar'; text: string; sub?: string | null};
export type QuoteEl = Span & {type: 'quote'; text: string; source: string; era?: string | null; side: 'left' | 'right'};
export type FactionBarEl = Span & {type: 'faction_bar'; text: string; faction: string | null; color: PersonColor};
export type SiegeEl = Span & {type: 'siege'; place: string; text: string; color: string | null};
export type CaptureEl = Span & {type: 'capture'; place: string; text: string; faction: string; color: string; fill: string};
export type AllianceEl = Span & {type: 'alliance'; place: string; text: string};
export type ReplayEl = Span & {type: 'replay'; points: string[]; label?: string | null; color?: string | null};
export type SpotEl = Span & {type: 'spot'; place: string; text?: string | null};
export type ActEl = Span & {type: 'act'; act: 'coins' | 'wind' | 'edict' | 'prison' | 'courier' | 'beacon' | 'execute' | 'mourn' | 'enthrone' | 'arrows' | 'flood' | 'night' | 'thunder' | 'catapult' | 'locusts' | 'fall' | 'refugees' | 'prop' | 'inkwash' | 'farm' | 'jianlv' | 'feint' | 'herd' | 'pontoon'; item?: string; n?: number; angle?: number; len?: number; offset?: [number, number]; radius?: number; size?: number; tone?: 'ink' | 'red'; image?: string | null; cutout?: boolean; name?: string; title?: string; place?: string | null; places?: string[]; text?: string | null; sub?: string | null; side?: 'left' | 'right'; dir?: 'left' | 'right'; color?: string; step?: number; grow?: number};
export type FireEl = Span & {type: 'fire'; place: string; on?: string; flash?: boolean; flash_at?: number; radius?: number; size?: number};
export type BreatheEl = Span & {type: 'breathe'; faction: string};
export type YearFlipEl = Span & {type: 'yearflip'; from: {era?: string | null; text: string}; to: {era?: string | null; text: string}};
export type ClashEl = Span & {type: 'clash'; place: string; sides: {faction: string; color: string; kind: 'cavalry' | 'infantry' | 'archer' | 'crossbow'; from: string | null; banner?: string}[]; title?: string; loser?: number; loser_at?: number; trace_end?: number; burn_side?: number; burn_at?: number};
export type StageActor = {who: string; name: string; title: string; image: string | null; cutout?: boolean; color: PersonColor; side: 'left' | 'right'; start: number; end: number; faces?: 'left' | 'right' | 'front'; die_at?: number; verb?: string};
export type StageEl = Span & {type: 'stage'; scene: string; image?: string | null; actors: StageActor[]; lines: {who: string; t0: number; t1: number; text: string; original: boolean}[]};
export type ForcesSide = {name: string; sub: string; color: PersonColor; image: string | null; faces?: 'left' | 'right' | 'front'};
export type ForcesEl = Span & {type: 'forces'; left: ForcesSide; right: ForcesSide; loser: 'left' | 'right' | null};
export type TacticEl = Span & {type: 'tactic'; layout: string; phase: 'deploy' | 'charge' | 'volley' | 'rout' | 'climb' | 'surround' | 'breakout'; title?: string | null; colors: {a: string; d: string}; banners?: {a?: string; d?: string}; first?: boolean; last?: boolean;
  labels?: {a?: string; d?: string; city?: string; mound?: string; charge?: string; climb?: string; ring?: string; out?: string; back?: string}};
export type Element = TacticEl | ForcesEl | StageEl | ActEl | FireEl | YearFlipEl | ClashEl | SiegeEl | CaptureEl | AllianceEl | ReplayEl | SpotEl | BreatheEl | CityEl | FlagEl | CampEl | TrailEl | VignetteEl | ArrowEl | BattleEl | CardEl | PortraitEl | HeadlineEl | RegionEl | StampEl | EnterEl | PersonCardEl | ExitEl | VersusEl | TitleBarEl | QuoteEl | FactionBarEl;

export type Region = {id: string; name: string; fill: string; edge: string; path: string; source: string; precision: string; anchor: [number, number] | null; main: boolean};

export type Territory = {
  cells: {id: string; name: string; zhou: string; path: string; anchor: [number, number]}[];
  polities: Record<string, {fill: string; edge: string; flag: string; main: boolean; atlas?: string}>;
  states: {t: number; owners: Record<string, string>; uncertain: string[]; outlines: Record<string, string>; labels: Record<string, [number, number]>; groups?: Record<string, string[][]>; origin?: [number, number]; ghost?: number; places?: Record<string, string>}[];
  zhou_labels: {name: string; x: number; y: number}[];
  jun_labels: boolean | 'always';
  precision: string;
  look?: 'light' | 'classic' | 'atlas';
  zhou_lines?: string[];
  cities?: {name: string; x: number; y: number; rank: number; jun?: string}[];   // always-on atlas towns: 1 = 郡治 (jun = its commandery's name), 2 = 县治
};

export type Theme = {
  paper: string;
  ink: string;
  red: string;
  blue: string;
  gold: string;
  river: string;
  captionBg: string;
  yearBg: string;
  ui?: 'clean' | 'full';
  look?: 'light' | 'classic' | 'atlas';   // atlas = 史图记忆簿-style map (2026-10-15)
  palette?: 'warm' | null;   // warm = 地图知天下-style pale base, sans map type (2026-10-24)
  series_title?: string;
  channel?: string;
};

export type Episode = {
  schema: 'history-studio-episode/1';
  id: string;
  build: string;
  title: string;
  series: string;
  fps: number;
  width: number;
  height: number;
  duration: number;
  theme: Theme;
  map: {
    km?: number;   // world px per km at zoom 1 (screen px per km = km × camera zoom)
    raster: null | {src: string; x: number; y: number; width: number; height: number};
    minimap?: null | {x: number; y: number; width: number; height: number; zoom: number};
    rivers: {name: string; path: string; rank?: number}[];
    regions: Region[];
    watermark?: string;
    river_overlay?: {src: string; x: number; y: number; width: number; height: number};
    features?: {name: string; kind: 'mountain' | 'water' | 'sea'; x: number; y: number; v: boolean}[];
  };
  places: Place[];
  segments: Segment[];
  camera: CameraKey[];
  phases: (Span & {text: string})[];
  years: (Span & {text: string; era?: string | null})[];
  elements: Element[];
  audio: string | null;
  legend: string[];
  territory?: Territory | null;
  footer: {left: string; right: string};
};
