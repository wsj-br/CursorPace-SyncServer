"""Backup export/import of the app backup zip format (spec section 7)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from .merge import (
    normalize_decimal,
    normalize_timestamp,
    utc_now_canonical,
)


FORMAT_VERSION = 1
PRODUCT = "CursorPace"


def _renewal_day(cycle_start_local: str) -> int:
    # cycle_start is local wall-clock ISO; day number is the date's day.
    return datetime.fromisoformat(cycle_start_local).day


def build_export_zip(
    *,
    samples: list[dict[str, str]],
    cycle_start_utc: str | None,
    active_cycle: dict[str, str] | None,
    cycle_history: list[dict[str, str]],
) -> bytes:
    ordered = sorted(samples, key=lambda s: s["ts"])

    manifest = {
        "formatVersion": FORMAT_VERSION,
        "product": PRODUCT,
        "createdUtc": utc_now_canonical(),
    }

    if active_cycle is not None:
        active_out = {
            "renewalDay": _renewal_day(active_cycle["cycle_start"]),
            "cycleStart": active_cycle["cycle_start"],
            "nextRenewal": active_cycle["next_renewal"],
        }
    else:
        active_out = None
    history_out = [
        {
            "renewalDay": _renewal_day(e["cycle_start"]),
            "cycleStart": e["cycle_start"],
            "nextRenewal": e["next_renewal"],
        }
        for e in sorted(cycle_history, key=lambda e: e["cycle_start"])
    ]
    settings: dict[str, object] = {
        "version": 2,
        "activeCycle": active_out,
        "cycleHistory": history_out,
    }
    if active_cycle is not None:
        settings["cursorAccountConnected"] = True

    # usage-samples: numbers as JSON numbers (spec allows numbers).
    usage_samples_list: list[dict[str, object]] = []
    for s in ordered:
        try:
            cursor_num: object = float(s["cursor"])
            other_num: object = float(s["other"])
            # Keep ints as ints for cleaner output.
            if float(s["cursor"]).is_integer():
                cursor_num = int(float(s["cursor"]))
            if float(s["other"]).is_integer():
                other_num = int(float(s["other"]))
        except ValueError:
            cursor_num = s["cursor"]
            other_num = s["other"]
        usage_samples_list.append(
            {"ts": s["ts"], "cursor": cursor_num, "other": other_num}
        )
    usage = {
        "version": 1,
        "cycleStartUtc": cycle_start_utc,
        "samples": usage_samples_list,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("settings.json", json.dumps(settings, indent=2))
        zf.writestr("usage-samples.json", json.dumps(usage, indent=2))
    return buf.getvalue()


def _validate_local_bounds(start: object, end: object) -> bool:
    if not isinstance(start, str) or not isinstance(end, str):
        return False
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        return False
    return end_dt > start_dt


def parse_import_zip(data: bytes) -> dict[str, object]:
    """Parse an app/server backup zip. Raises ValueError with a message."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("not a valid zip file") from exc

    with zf:
        names = set(zf.namelist())

        # manifest.json: allowed to be missing (old backups).
        if "manifest.json" in names:
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid manifest.json") from exc
            if manifest.get("product") != PRODUCT:
                raise ValueError(
                    f"unsupported product: {manifest.get('product')!r}"
                )
            version = manifest.get("formatVersion", 1)
            if isinstance(version, bool) or not isinstance(version, int):
                raise ValueError("invalid formatVersion")
            if version > FORMAT_VERSION:
                raise ValueError(
                    f"unsupported formatVersion: {version}"
                )

        # settings.json bounds (missing -> no cycles).
        active_cycle: dict[str, str] | None = None
        cycle_history: list[dict[str, str]] = []
        if "settings.json" in names:
            try:
                settings = json.loads(
                    zf.read("settings.json").decode("utf-8")
                )
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid settings.json") from exc
            raw_active = settings.get("activeCycle")
            if isinstance(raw_active, dict):
                start = raw_active.get("cycleStart")
                end = raw_active.get("nextRenewal")
                if _validate_local_bounds(start, end):
                    assert isinstance(start, str) and isinstance(end, str)
                    active_cycle = {
                        "cycle_start": start,
                        "next_renewal": end,
                    }
            raw_history = settings.get("cycleHistory")
            if isinstance(raw_history, list):
                for entry in raw_history:
                    if not isinstance(entry, dict):
                        continue
                    start = entry.get("cycleStart")
                    end = entry.get("nextRenewal")
                    if _validate_local_bounds(start, end):
                        assert isinstance(start, str) and isinstance(
                            end, str
                        )
                        cycle_history.append(
                            {
                                "cycle_start": start,
                                "next_renewal": end,
                            }
                        )

        # usage-samples.json (missing -> empty samples).
        samples: list[dict[str, str]] = []
        cycle_start_utc: str | None = None
        if "usage-samples.json" in names:
            try:
                usage = json.loads(
                    zf.read("usage-samples.json").decode("utf-8")
                )
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid usage-samples.json") from exc
            raw_cycle = usage.get("cycleStartUtc")
            if raw_cycle is not None:
                if not isinstance(raw_cycle, str):
                    raise ValueError("invalid cycleStartUtc")
                try:
                    cycle_start_utc = normalize_timestamp(raw_cycle)
                except ValueError as exc:
                    raise ValueError(
                        f"invalid cycleStartUtc: {raw_cycle!r}"
                    ) from exc
            raw_samples = usage.get("samples", [])
            if not isinstance(raw_samples, list):
                raise ValueError("invalid samples list")
            for i, entry in enumerate(raw_samples):
                if not isinstance(entry, dict):
                    raise ValueError(f"samples[{i}]: not an object")
                for field in ("ts", "cursor", "other"):
                    if field not in entry:
                        raise ValueError(f"samples[{i}]: missing {field!r}")
                try:
                    ts = normalize_timestamp(str(entry["ts"]))
                except ValueError as exc:
                    raise ValueError(
                        f"samples[{i}]: bad timestamp"
                    ) from exc
                try:
                    cursor = normalize_decimal(entry["cursor"])
                    other = normalize_decimal(entry["other"])
                except ValueError as exc:
                    raise ValueError(
                        f"samples[{i}]: bad decimal"
                    ) from exc
                samples.append(
                    {"ts": ts, "cursor": cursor, "other": other}
                )
            samples.sort(key=lambda s: s["ts"])

    return {
        "samples": samples,
        "cycle_start_utc": cycle_start_utc,
        "active_cycle": active_cycle,
        "cycle_history": cycle_history,
    }
