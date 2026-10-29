"""Time-aware historical places and separate sourced relation types.

This catalog is deliberately independent of the legacy pixel-map compiler.
Imported records are research candidates until explicitly reviewed.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "catalog" / "historical_places.json"
RELATION_TYPES = {"administrative_parent", "political_affiliation", "de_facto_control",
                  "garrison", "presence", "fief"}


def normalize(value):
    return "".join(str(value).casefold().split())


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(data):
    errors = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    ids = set()
    sources = {s["source_id"] for s in data.get("sources", [])}
    if len(sources) != len(data.get("sources", [])):
        errors.append("duplicate source_id")
    for place in data.get("places", []):
        pid = place.get("place_id")
        if not pid or pid in ids:
            errors.append(f"missing or duplicate place_id: {pid}")
        ids.add(pid)
        coords = place.get("location", {}).get("coordinates")
        if (not isinstance(coords, list) or len(coords) != 2 or
                any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in coords) or
                not -180 <= coords[0] <= 180 or not -90 <= coords[1] <= 90):
            errors.append(f"{pid}: invalid lon/lat")
        if place.get("location", {}).get("crs") != "EPSG:4326":
            errors.append(f"{pid}: normalized location must use EPSG:4326")
        for item in [place.get("location", {}), *place.get("names", [])]:
            if not item.get("source_refs"):
                errors.append(f"{pid}: missing source_refs")
            for source in item.get("source_refs", []):
                if source not in sources:
                    errors.append(f"{pid}: missing source {source}")
            if item.get("valid_from") is not None and item.get("valid_to") is not None:
                if item["valid_from"] > item["valid_to"]:
                    errors.append(f"{pid}: reversed name interval")
    rids = set()
    for rel in data.get("relations", []):
        rid = rel.get("relation_id")
        if not rid or rid in rids:
            errors.append(f"missing or duplicate relation_id: {rid}")
        rids.add(rid)
        if rel.get("place_id") not in ids:
            errors.append(f"{rid}: missing place")
        if rel.get("relation_type") not in RELATION_TYPES:
            errors.append(f"{rid}: unsupported relation_type")
        for source in rel.get("source_refs", []):
            if source not in sources:
                errors.append(f"{rid}: missing source {source}")
        if rel.get("review_status") == "reviewed":
            if not rel.get("source_refs") or not rel.get("entity_id"):
                errors.append(f"{rid}: reviewed relationship needs evidence and entity")
            interval = rel.get("interval", {})
            if interval.get("basis") == "event_order":
                if interval.get("start_order") is None or interval.get("end_order") is None:
                    errors.append(f"{rid}: event_order needs explicit start/end bounds")
                elif interval["start_order"] >= interval["end_order"]:
                    errors.append(f"{rid}: empty or reversed event interval")
                if interval.get("story_year") is None:
                    errors.append(f"{rid}: event_order needs story_year")
            elif interval.get("basis") == "year":
                if interval.get("start_year") is None or interval.get("end_year") is None:
                    errors.append(f"{rid}: year interval needs explicit start/end bounds")
                elif interval["start_year"] >= interval["end_year"]:
                    errors.append(f"{rid}: empty or reversed year interval")
            elif interval.get("basis") == "snapshot":
                if not interval.get("snapshot_id") or interval.get("story_year") is None:
                    errors.append(f"{rid}: snapshot needs an identifier and year")
            else:
                errors.append(f"{rid}: reviewed relationship needs temporal basis")
    if errors:
        raise ValueError("\n".join(errors))
    return data


def load(path=DEFAULT):
    return validate(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def year_matches(name, year):
    # Name intervals imported from legacy entries are explicitly inclusive.
    return ((name.get("valid_from") is None or year >= name["valid_from"]) and
            (name.get("valid_to") is None or year <= name["valid_to"]))


def active_relation(rel, year, event_order, snapshot=None):
    interval = rel.get("interval", {})
    if interval.get("basis") == "snapshot":
        return snapshot is not None and interval["snapshot_id"] == snapshot and interval["story_year"] == year
    if interval.get("basis") == "event_order":
        return (event_order is not None and interval.get("story_year") == year and
                interval["start_order"] <= event_order < interval["end_order"])
    if interval.get("basis") == "year":
        return interval["start_year"] <= year < interval["end_year"]
    return False


def resolve(data, query, year, event_order=None, snapshot=None):
    wanted = normalize(query)
    matches = [p for p in data["places"] if wanted in
               {normalize(p["place_id"]), *map(normalize, p.get("aliases", [])),
                *(normalize(n["text"]) for n in p["names"])}]
    if len(matches) != 1:
        raise ValueError(f"expected one place for {query!r}, found {[p['place_id'] for p in matches]}")
    place = matches[0]
    names = [n for n in place["names"] if year_matches(n, year)]
    if len(names) != 1:
        raise ValueError(f"{place['place_id']}: {len(names)} applicable names for {year}")
    chosen = names[0]
    if wanted in {normalize(n["text"]) for n in place["names"]} and wanted != normalize(chosen["text"]):
        raise ValueError(f"anachronistic name {query}; use {chosen['text']} for {year}")
    states = {}
    for kind in sorted(RELATION_TYPES):
        candidates = [r for r in data.get("relations", []) if r["place_id"] == place["place_id"]
                      and r["relation_type"] == kind]
        active = [r for r in candidates if r.get("review_status") == "reviewed"
                  and active_relation(r, year, event_order, snapshot)]
        entities = {r["entity_id"] for r in active}
        multi_allowed = kind in {"garrison", "presence"}
        status = "unknown" if not active else "known"
        if len(entities) > 1 and not multi_allowed:
            status = "conflict"
        if any(r.get("state") == "contested" for r in active):
            status = "contested"
        states[kind] = {"status": status, "records": active,
                        "candidate_record_ids": [r["relation_id"] for r in candidates
                                                 if r.get("review_status") != "reviewed"]}
    return {"place_id": place["place_id"], "year": year, "event_order": event_order, "snapshot": snapshot,
            "name": chosen, "location": place["location"], "relations": states}


def export_geojson(data, place_ids, year, technical_preview=False):
    features = []
    for pid in place_ids:
        result = resolve(data, pid, year)
        if not technical_preview and (result["name"]["review_status"] != "reviewed" or
                                      result["location"]["review_status"] != "reviewed"):
            raise ValueError(f"{pid}: unreviewed name or coordinate; use explicit technical preview only")
        features.append({"type": "Feature", "geometry": {"type": "Point",
                         "coordinates": result["location"]["coordinates"]},
                         "properties": {"place_id": pid, "name": result["name"]["text"],
                                        "year": year, "preview_only": technical_preview,
                                        "coordinate_meaning": result["location"]["meaning"],
                                        "source_refs": result["location"]["source_refs"]}})
    return {"type": "FeatureCollection", "features": features}


def import_legacy(source, destination):
    if Path(destination).exists():
        raise ValueError("destination already exists; migration never overwrites research")
    old = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    data = {"schema_version": 1, "interval_rules": {"names": "inclusive", "relations": "start inclusive, end exclusive"},
            "sources": [], "places": [], "relations": [], "events": []}
    for item in old["places"]:
        pid = item["id"]
        for role in ("name", "coordinate"):
            data["sources"].append({"source_id": f"{pid}.{role}", "locator": item[f"{role}Source"],
                                    "status": "legacy_reference_needs_review"})
        data["places"].append({"place_id": pid, "type": "city_site", "aliases": item["aliases"],
            "location": {"coordinates": item["coordinates"], "crs": "EPSG:4326",
                         "meaning": item["coordinatePrecision"], "accuracy_m": None,
                         "source_refs": [f"{pid}.coordinate"], "review_status": "needs_review"},
            "names": [{"text": n["text"], "valid_from": n["from"], "valid_to": n["to"],
                       "source_refs": [f"{pid}.name"], "review_status": "needs_review"} for n in item["names"]],
            "review_note": item.get("reviewNote", "")})
    dump(destination, validate(data))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", type=Path, default=DEFAULT)
    subs = ap.add_subparsers(dest="command", required=True)
    subs.add_parser("validate")
    seed = subs.add_parser("import-legacy")
    seed.add_argument("--source", type=Path, default=HERE / "places_curated.json")
    lookup = subs.add_parser("lookup")
    lookup.add_argument("query")
    lookup.add_argument("--year", type=int, required=True)
    lookup.add_argument("--event-order", type=int)
    lookup.add_argument("--snapshot", help="Named researched historical state; never assumed for an entire year")
    export = subs.add_parser("export")
    export.add_argument("--places", nargs="+", required=True)
    export.add_argument("--year", type=int, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--technical-preview", action="store_true")
    args = ap.parse_args()
    if args.command == "import-legacy":
        import_legacy(args.source, args.catalog)
        print("Imported research candidates; no ownership inferred.")
        return
    data = load(args.catalog)
    if args.command == "lookup":
        print(json.dumps(resolve(data, args.query, args.year, args.event_order, args.snapshot), ensure_ascii=False, indent=2))
    elif args.command == "export":
        dump(args.output, export_geojson(data, args.places, args.year, args.technical_preview))
        print(str(args.output.resolve()))
    else:
        print(f"Valid: {len(data['places'])} places, {len(data['relations'])} relationships")


if __name__ == "__main__":
    main()
