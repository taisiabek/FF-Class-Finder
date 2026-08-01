#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

API_URL = "https://uae.fitnessfirstme.com/api/public/sentinel/class-timetable"

CLUBS = {
    "ABN": "Al Barsha Mall",
    "ADM": "Abu Dhabi Mall",
    "AFA": "Forsan Central",
    "ASA": "Al Seef Village Mall",
    "AWA": "Al Wahda",
    "BGD": "Bay Gate Dubai",
    "BJC": "Burjuman Centre",
    "BML": "Bawabat Mall Ladies",
    "DCC": "Deira City Centre",
    "DHL": "Damac Hills Ladies",
    "DMA": "Dalma Mall",
    "DMN": "Media City",
    "DSO": "Dubai Silicon Oasis",
    "FCD": "Festival City Dubai",
    "FGD": "Financial Gate Dubai",
    "IBM": "Ibn Battuta Mall",
    "MCC": "Mirdif City Centre",
    "MGD": "Marina Gate Dubai",
    "MMA": "Marina Mall",
    "MRD": "Mudon Ranches Dubai",
    "OCD": "Oasis Centre Dubai",
    "SSC": "Sharjah Sahara Center",
    "TPD": "The Palm Dubai",
    "UML": "Uptown Mirdif Ladies",
    "WHA": "Wahat Hili",
    "ZSS": "Zero 6 Sharjah",
}

DUBAI_CODES = {
    "ABN", "BGD", "BJC", "DCC", "DHL", "DMN", "DSO", "FCD",
    "FGD", "IBM", "MCC", "MGD", "MRD", "OCD", "TPD", "UML",
}

REMOVED_INSTRUCTORS = {"Ahmed Madkour", "Taylor Araujo De Souza"}

def post_json(payload: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://uae.fitnessfirstme.com",
            "Referer": "https://uae.fitnessfirstme.com/timetable",
            "User-Agent": "Mozilla/5.0 FF-Class-Finder-Schedule-Updater/1.0",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 3)
    raise RuntimeError(f"API request failed after {retries} attempts: {last_error}")

def classify(item: dict[str, Any]) -> tuple[str, str]:
    master = str(item.get("MasterClass") or "").strip()
    class_name = str(item.get("ClassName") or "").strip()
    s = f"{master} {class_name}".lower()

    if any(k in s for k in (
        "sound healing", "sound bath", "meditation", "sensory flow",
        "breathwork", "breathing", "mindfulness",
    )):
        return "Recovery / Mindfulness", "Recovery / Mindfulness"
    if "bodypump" in s:
        return "BodyPump", "Strength"
    if "reform" in s:
        return "Reformer Pilates", "Stability / Mobility"
    if any(k in s for k in ("box", "bodycombat", "combat", "kickbox", "hydrokombat")):
        return "Boxing & combat", "HIIT / VO₂max"
    if any(k in s for k in ("rpm", "cycling", "myride")):
        return "Cycling", "Cardio / Zone 2"
    if any(k in s for k in ("zumba", "bodyjam", "dance", "afro", "belly", "bollywood")):
        return "Dance", "Cardio / Zone 2"
    if any(k in s for k in ("yoga", "bodybalance", "swing yoga")):
        return "Yoga", "Stability / Mobility"
    if "pilates" in s:
        return "Pilates", "Stability / Mobility"
    if any(k in s for k in ("stretch", "mobility", "myoflow", "animal flow")):
        return "Mobility", "Stability / Mobility"
    if "barre" in s:
        return "Barre", "Stability / Mobility"
    if "trx" in s:
        return "TRX", "Strength"
    if "core" in s:
        return "Core", "Stability / Mobility"
    if any(k in s for k in (
        "strength", "body conditioning", "push press", "kettlebell",
        "resistance", "power", "bodypump",
    )):
        return "Strength", "Strength"
    if any(k in s for k in (
        "tabata", "strong nation", "bodyattack", "rush", "tuff", "x45",
        "grit cardio", "hiit", "bootcamp", "metcon",
    )):
        return "HIIT & conditioning", "HIIT / VO₂max"
    if any(k in s for k in ("step", "jump")):
        return "Step & jump", "Cardio / Zone 2"
    if any(k in s for k in ("aqua", "hydro")):
        return "Aqua", "Cardio / Zone 2"
    if "run" in s:
        return "Running", "Cardio / Zone 2"

    return master or class_name or "Other", "Other / mixed"

def fetch_schedule(start: date, end: date) -> list[dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    failures: list[str] = []

    for code, name in CLUBS.items():
        payload = {
            "FromCalendarDate": start.isoformat(),
            "ToCalendarDate": end.isoformat(),
            "LocationCode": code,
        }
        try:
            response = post_json(payload)
            items = response.get("data") if isinstance(response, dict) else None
            if not isinstance(items, list):
                raise RuntimeError(f"Unexpected response: {str(response)[:250]}")
            print(f"{code} {name}: {len(items)}")
            for raw in items:
                item = dict(raw)
                trainer = str(item.get("TrainerName") or "").strip()
                if trainer in REMOVED_INSTRUCTORS:
                    continue
                item["TrainerName"] = trainer
                item["_region"] = "Dubai" if code in DUBAI_CODES else "Other UAE"
                family, primary = classify(item)
                item["_modality"] = family
                item["_family"] = family
                item["_primary"] = primary
                all_items.append(item)
        except Exception as exc:
            failures.append(f"{code}: {exc}")

    if failures:
        raise RuntimeError("Some clubs failed:\n" + "\n".join(failures))

    unique: dict[str, dict[str, Any]] = {}
    for item in all_items:
        slot_id = item.get("SlotBookingId")
        key = str(slot_id) if slot_id is not None else "|".join(
            str(item.get(k) or "")
            for k in ("LocationCode", "ClassDateTime", "ClassName", "TrainerName")
        )
        unique[key] = item

    result = sorted(
        unique.values(),
        key=lambda x: (
            str(x.get("ClassDateTime") or ""),
            str(x.get("LocationName") or ""),
            str(x.get("ClassName") or ""),
        ),
    )

    if len(result) < 300:
        raise RuntimeError(f"Safety check failed: only {len(result)} classes fetched")

    core_codes = {"ABN", "TPD", "DMN", "MGD", "BGD", "DSO", "IBM", "DHL"}
    present_codes = {str(x.get("LocationCode") or "") for x in result}
    missing_core = sorted(core_codes - present_codes)
    if missing_core:
        raise RuntimeError(f"Safety check failed: no classes for core clubs {missing_core}")

    return result

def replace_embedded_data(index_path: Path, schedule: list[dict[str, Any]]) -> None:
    html = index_path.read_text(encoding="utf-8")
    payload = json.dumps(schedule, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pattern = re.compile(r"const DATA=.*?;\s*const \$=", re.S)
    replacement = f"const DATA={payload}; const $="
    updated, count = pattern.subn(lambda _: replacement, html, count=1)
    if count != 1:
        raise RuntimeError("Could not locate embedded DATA in index.html")
    index_path.write_text(updated, encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="index.html")
    parser.add_argument("--days", type=int, default=21)
    args = parser.parse_args()

    start = date.today()
    end = start + timedelta(days=args.days)
    schedule = fetch_schedule(start, end)
    replace_embedded_data(Path(args.index), schedule)
    print(f"Updated {args.index}: {len(schedule)} classes, {start} through {end}")

if __name__ == "__main__":
    main()
