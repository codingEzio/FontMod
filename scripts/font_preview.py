"""Catalog-driven specimens for the existing fontmod CLI and portable web kit.

Callers select current assets and supply URLs relative to preview.html. This
module neither looks up installed faces nor downloads network assets.
"""
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import math
import os
import uuid
import subprocess
import sys
import time
import fcntl
import urllib.request
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from fontTools.ttLib import TTFont


# These probes describe only the displayed sample, never whole-script coverage.
COVERAGE_SAMPLES = {
    "英文示例": "A small detail changes the rhythm of a page. 0123456789",
    "中文示例": "把日常排成自己的样子清晨的光落在桌边新的想法从一行字开始中文简体繁體",
    "韩文示例": "가나다라마바사안녕하세요",
    "Nerd 图标示例（5 码位）": "\ue0b0\ue0a0\uf07b\uf120\uf013",
    "Emoji 示例码位（序列另验）": "😀❤👍🏽👩💻🇹🇼\u20e3",
}
HISTORICAL_STATIC_TALL = {"DotoMod700ZhRefinedTall", "DotoMod700ZhRefinedCondensedTall"}


def normalize_entry(entry):
    """Normalize a caller-selected face without inventing coverage claims."""
    item = dict(entry)
    if not isinstance(item.get("family"), str) or not item["family"].strip():
        raise ValueError("Preview entry needs a family name")
    font_url = item.get("fontUrl")
    if not isinstance(font_url, str) or not font_url.strip():
        raise ValueError("Preview entry needs a fontUrl: " + item["family"])
    parts = urlsplit(font_url)
    if parts.scheme or parts.netloc:
        raise ValueError("Preview fonts must use local relative URLs: " + font_url)
    item.setdefault("label", item["family"])
    item.setdefault("metadataWeight", 400)
    item.setdefault("sourceWeight", None)
    item.setdefault("coverage", [])
    for coverage in item["coverage"]:
        if coverage.get("status", "unknown") not in {"embedded", "partial", "fallback", "unknown"}:
            raise ValueError("Unknown preview coverage status")
    styles = item.get("styles")
    if styles is None:
        heights = item.get("heights")
        styles = ([{"name": name, "coordinates": {"HGHT": round(scale * 100, 6)}}
                   for name, scale in heights.items()] if heights else [{"name": "Regular"}])
    if not styles:
        raise ValueError("Preview entry needs at least one style")
    normalized = []
    for style in styles:
        value = dict(style)
        if not isinstance(value.get("name"), str) or not value["name"].strip():
            raise ValueError("Preview style needs a name")
        coordinates = value.get("coordinates", {})
        for axis, coordinate in coordinates.items():
            if not re.fullmatch(r"[A-Za-z0-9 ]{4}", axis):
                raise ValueError("Invalid preview axis: " + axis)
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not math.isfinite(coordinate):
                raise ValueError("Invalid preview axis coordinate")
        value["coordinates"] = coordinates
        normalized.append(value)
    item["styles"] = normalized
    return item


def write_catalog(destination, entries, title="字体样本册"):
    """Write preview_catalog.json and return the exact portable catalog."""
    catalog = {"schemaVersion": 1, "title": title,
               "generatedAt": datetime.now(timezone.utc).isoformat(),
               "families": [normalize_entry(entry) for entry in entries]}
    if not catalog["families"]:
        raise ValueError("Preview catalog cannot be empty")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    return catalog


def _sha(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _read_json(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def _source_weight(provenance, recipe):
    for value in (provenance.get("sourceWeight"),
                  provenance.get("verification", {}).get("sourceWeight")
                  if isinstance(provenance.get("verification"), dict) else None,
                  recipe.get("axes", {}).get("wght")):
        if value is not None:
            return value
    return None


def _source_label(sources):
    if isinstance(sources.get("text"), dict):
        sources = sources["text"]
    return " + ".join(value["label"] for value in sources.values()
                      if isinstance(value, dict) and isinstance(value.get("label"), str))


def _probe_coverage(cmap):
    probes = []
    for label, sample in COVERAGE_SAMPLES.items():
        codepoints = sorted({ord(character) for character in sample if not character.isspace()})
        present = [value for value in codepoints if value in cmap]
        status = "embedded" if len(present) == len(codepoints) else "partial" if present else "fallback"
        probes.append({"label": label, "status": status, "sampleCodepoints": codepoints,
                       "presentCount": len(present), "sampleCount": len(codepoints),
                       "missingCodepoints": [value for value in codepoints if value not in cmap]})
    return probes


def _font_entry(file, links, label=None, source_label=None, provenance=None, recipe=None, kind="source"):
    """Read exact source metadata; the preview does not imply installation."""
    path = Path(file).expanduser().resolve(strict=True)
    digest = _sha(path)
    link = links / (digest[:8] + "-" + path.name)
    if link.is_symlink():
        if link.resolve() != path:
            old=link.resolve()
            if not old.is_file() or _sha(old)!=digest:
                raise ValueError("Preview font link points to another source: " + str(link))
            # An asset may move from staging to its pinned/durable source while
            # keeping identical bytes. Refresh only this generated link.
            temporary=links/("delete_after_use_"+uuid.uuid4().hex)
            temporary.symlink_to(path);os.replace(temporary,link)
    elif link.exists():
        raise ValueError("Preview font link name is occupied: " + str(link))
    else:
        link.symlink_to(path)
    provenance, recipe = provenance or {}, recipe or {}
    with TTFont(path, lazy=True) as font:
        names = font["name"]
        family = names.getDebugName(16) or names.getDebugName(1) or path.stem
        metadata_weight = int(font["OS/2"].usWeightClass) if "OS/2" in font else 400
        styles = []
        if "fvar" in font:
            for index, instance in enumerate(font["fvar"].instances):
                styles.append({"name": names.getDebugName(instance.subfamilyNameID) or f"Instance {index + 1}",
                               "coordinates": dict(instance.coordinates)})
            if not styles:
                styles = [{"name": "Regular", "coordinates": {axis.axisTag: axis.defaultValue
                                                                        for axis in font["fvar"].axes}}]
        else:
            styles = [{"name": "Regular", "coordinates": {}}]
        coverage = _probe_coverage(font.getBestCmap() or {})
        color = any(table in font for table in ("sbix", "CBDT", "COLR", "SVG "))
        glyph_count = int(font["maxp"].numGlyphs)
    by_label = {value["label"]: value for value in coverage}
    item = {"family": family, "label": label or family, "fontUrl": "fonts/" + link.name,
            "styles": styles, "sourceWeight": _source_weight(provenance, recipe),
            "metadataWeight": metadata_weight, "sourceLabel": source_label or "",
            "coverage": coverage, "emoji": {"status": by_label["Emoji 示例码位（序列另验）"]["status"],
                                               "label": "彩色字体；序列另验" if color else "样例码位；系统可能补字"},
            "icons": {"status": by_label["Nerd 图标示例（5 码位）"]["status"]},
            "hangul": {"status": by_label["韩文示例"]["status"]},
            "sourceFile": str(path), "sha256": digest, "bytes": path.stat().st_size,
            "glyphCount": glyph_count, "kind": kind,
            "installationStatus": "not-checked"}
    horizontal_scale = provenance.get("horizontalScale", recipe.get("horizontalScale"))
    if horizontal_scale is not None:
        item["horizontalScale"] = horizontal_scale
    return normalize_entry(item)


def prepare_local(root, family_names, extras=(), include_archived=False):
    """Materialize the selected current-family/static/source catalog, no copying fonts.

    Current Families are explicit. Outputs are current static release pointers;
    historical 700 Tall prototypes are excluded. Extra sources must be explicit
    file paths and may add display/source labels. Existing fonts are untouched.
    """
    root = Path(root).resolve(strict=True)
    destination = root / ".cache/FontPreview"
    links = destination / "fonts"
    links.mkdir(parents=True, exist_ok=True)
    selection = root / "font_catalog.json"
    archived = set(_read_json(selection).get("archivedFamilies", [])) if selection.is_file() else set()
    entries = []
    selected_sources = set()
    for name in family_names:
        if name in archived and not include_archived:
            continue
        directory = root / "Families" / name
        provenance = _read_json(directory / "provenance.json")
        recipe = _read_json(directory / "family.json")
        sources = _read_json(directory / "sources.json")
        file = directory / (name + ".woff2")
        if not file.is_file():
            file = directory / (name + ".ttf")
        entry = _font_entry(file, links, provenance=provenance, recipe=recipe,
                            source_label=_source_label(sources), kind="current-family")
        entries.append(entry)
        selected_sources.add(entry["sourceFile"])
    outputs = root / "Outputs"
    for directory in sorted(outputs.iterdir()) if outputs.is_dir() and not (root / "final_fonts.json").exists() else ():
        if not directory.is_dir() or directory.name.startswith(".") or directory.name in HISTORICAL_STATIC_TALL:
            continue
        file = directory / (directory.name + ".woff2")
        if not file.is_file():
            file = directory / (directory.name + ".ttf")
        if not file.is_file():
            raise ValueError("Current static output has no font: " + str(directory))
        entry = _font_entry(file, links, provenance=_read_json(directory / "provenance.json"),
                            recipe=_read_json(directory / "recipe.json"),
                            source_label=_source_label(_read_json(directory / "sources.json")),
                            kind="current-static")
        if entry["sourceFile"] not in selected_sources:
            entries.append(entry)
            selected_sources.add(entry["sourceFile"])
    for extra in extras:
        entry = _font_entry(extra["file"], links, label=extra.get("label"),
                            source_label=extra.get("sourceLabel"), kind="custom-source")
        if extra.get("expectedSha256") and entry["sha256"] != extra["expectedSha256"]:
            raise ValueError("Preferred preview source hash mismatch: " + entry["family"])
        for key in ("previewOnly", "previewGroup", "previewRank", "emojiOnly", "emojiSample", "bundleAdapter", "bundleName"):
            if key in extra:
                entry[key] = extra[key]
        entry["distribution"] = extra.get("distribution", "source-notices-required")
        if extra.get("packageDirectory"):
            entry["packageDirectory"] = str((root / extra["packageDirectory"]).resolve())
        if extra.get("webManifest"):
            manifest_path = (root / extra["webManifest"]).resolve(strict=True)
            manifest = _read_json(manifest_path)
            if manifest["source_sha256"] != entry["sha256"]:
                raise ValueError("Web subsets were built from a different font: " + str(manifest_path))
            entry["fontFiles"] = []
            for part in manifest["parts"]:
                source = manifest_path.parent / part["file"]
                if _sha(source) != part["sha256"]:
                    raise ValueError("Web subset hash mismatch: " + str(source))
                link = links / (part["sha256"][:8] + "-" + source.name)
                if link.is_symlink() and link.resolve() != source:
                    raise ValueError("Web subset link points to another source: " + str(link))
                if not link.exists():
                    link.symlink_to(source)
                ranges = ["U+%X" % start if start == end else "U+%X-%X" % (start, end)
                          for start, end in part["unicode_ranges"]]
                entry["fontFiles"].append({"fontUrl": "fonts/" + link.name, "unicodeRange": ",".join(ranges),
                                           "sha256": part["sha256"], "bytes": part["bytes"]})
            entry["fontUrl"] = entry["fontFiles"][0]["fontUrl"]
            entry["webBytes"] = sum(part["bytes"] for part in manifest["parts"])
        if entry["sourceFile"] not in selected_sources:
            entries.append(entry)
            selected_sources.add(entry["sourceFile"])
    entries.sort(key=lambda entry: entry.get("previewRank", 1000))
    shutil.copyfile(root / "templates/web_bundle/preview.html", destination / "preview.html")
    catalog = write_catalog(destination / "preview_catalog.json", entries, title="定制字体样本册")
    catalog["reopenCommand"] = str(root / "fontmod") + " catalog"
    (destination / "preview_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    return {"directory": str(destination), "previewFile": str(destination / "preview.html"),
            "catalogFile": str(destination / "preview_catalog.json"),
            "familyCount": len(entries), "styleCount": sum(len(item["styles"]) for item in entries),
            "sources": [{key: item[key] for key in ("family", "sourceFile", "sha256", "bytes", "kind")}
                        for item in catalog["families"]],
            "installationStatus": "not-checked", "historicalOutputsExcluded": sorted(HISTORICAL_STATIC_TALL)}


SERVICE = "fontmod-custom-catalog-v1"
_BACKGROUND_PROCESSES = []


def _health(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_fontmod_preview", timeout=.5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def open_catalog(root, family_names, extras=(), port=56134, open_browser=True, include_archived=False):
    """Rebuild the catalog, reuse its owned server, or detach one on a fixed port."""
    root = Path(root).resolve(strict=True)
    directory = root / ".cache/FontPreview"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "launch.lock").open("a") as lock:
        lock_deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= lock_deadline:
                    raise ValueError("Another catalog command is still preparing the preview; try again after it exits")
                time.sleep(.05)
        report = prepare_local(root, family_names, extras, include_archived=include_archived)
        health = _health(port)
        expected = str(directory)
        reused = bool(health and health.get("service") == SERVICE and health.get("directory") == expected)
        if not reused:
            import socket
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise ValueError(f"Preview port {port} belongs to another server; it was left untouched. Use --preview-port <free port>.")
            with (directory / "server.log").open("ab") as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", expected,
                                            "--port", str(port)], stdin=subprocess.DEVNULL, stdout=log,
                                           stderr=log, start_new_session=True, close_fds=True)
                # Retain the detached handle while this short-lived CLI exists.
                _BACKGROUND_PROCESSES.append(process)
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                health = _health(port)
                if health and health.get("service") == SERVICE and health.get("directory") == expected:
                    break
                if process.poll() is not None:
                    raise ValueError("Preview server failed to start; see " + str(directory / "server.log"))
                time.sleep(.05)
            else:
                process.terminate()
                process.wait(timeout=3)
                raise ValueError("Preview server did not become ready within 6 seconds")
        url = f"http://127.0.0.1:{port}/preview.html"
        if open_browser:
            subprocess.run(["/usr/bin/open", url], check=True)
        return dict(report, url=url, pid=health["pid"], reusedServer=reused,
                    browserOpened=open_browser, localOnly=True)


def serve(directory, host="127.0.0.1", port=0):
    """Serve an explicit local root; fail visibly on a port conflict."""
    directory = Path(directory).resolve(strict=True)
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/.cache/FontPreview/preview.html":
                self.send_response(302)
                self.send_header("Location", "/preview.html")
                self.end_headers()
            elif path == "/_fontmod_preview":
                payload = json.dumps({"service": SERVICE, "directory": str(directory), "pid": os.getpid()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                super().do_GET()

        def end_headers(self):
            # Font URLs contain a content digest; only the catalog/HTML changes in place.
            font_asset = urlsplit(self.path).path.startswith("/fonts/")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if font_asset else "no-cache")
            super().end_headers()

    handler = partial(Handler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as server:
        actual_port = server.server_address[1]
        runtime = {"directory": str(directory), "host": host, "port": actual_port,
                   "url": f"http://{host}:{actual_port}/preview.html", "pid": os.getpid(),
                   "startedAt": datetime.now(timezone.utc).isoformat(), "state": "running"}
        runtime_path = directory / "server.json"
        runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(runtime, ensure_ascii=False), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            runtime.update(state="stopped", stoppedAt=datetime.now(timezone.utc).isoformat())
            runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    options = parser.parse_args()
    serve(options.serve, port=options.port)
