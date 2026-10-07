"""Versioned, offline component catalog. Imports are validated atomically."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from urllib.parse import urlsplit
from pathlib import Path
from importlib.resources import files

from .models import GearSpec, finite

CSV_COLUMNS = ["sku", "supplier", "family", "module_mm", "teeth", "pressure_deg", "helix_deg",
               "width_mm", "bore_mm", "hub_diameter_mm", "hub_width_mm", "material",
               "bending_nm", "contact_nm", "price", "currency", "source_url", "rating_conditions", "retrieved_date"]


class Catalog:
    def __init__(self, path: Path | str = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gears (sku TEXT PRIMARY KEY, supplier TEXT NOT NULL,
          family TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, data TEXT NOT NULL);
        """)
        version = self.connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
        if version and version[0] != "1":
            raise ValueError("Unsupported catalog database schema")
        self.connection.execute("INSERT OR IGNORE INTO metadata VALUES ('schema','1')")
        if not self.connection.execute("SELECT COUNT(*) FROM gears").fetchone()[0]:
            self.import_csv(files("gearforge").joinpath("data/gears.csv").read_text())
        self.connection.commit()

    def close(self):
        self.connection.close()

    def rows(self, query: str = "") -> list[dict]:
        rows = self.connection.execute("SELECT data FROM gears ORDER BY supplier, sku").fetchall()
        result = [json.loads(row[0]) for row in rows]
        return [r for r in result if query.lower() in " ".join(map(str, r.values())).lower()]

    def gears(self, supplier="", family="spur", currency="USD") -> list[GearSpec]:
        specs = []
        for r in self.rows():
            if r["family"] != family or (supplier and supplier.lower() not in r["supplier"].lower()):
                continue
            specs.append(GearSpec(
                teeth=r["teeth"], module_mm=r["module_mm"], width_mm=r["width_mm"], bore_mm=r["bore_mm"],
                source="catalog", sku=r["sku"], pressure_deg=r["pressure_deg"], helix_deg=r["helix_deg"],
                hub_diameter_mm=r["hub_diameter_mm"], hub_width_mm=r["hub_width_mm"],
                bending_nm=r["bending_nm"], contact_nm=r["contact_nm"],
                price=r["price"] if r["currency"] == currency else None,
                source_url=r["source_url"], rating_conditions=r["rating_conditions"], material=r["material"],
                internal=r["family"] == "ring"))
        return specs

    def import_csv(self, text: str) -> int:
        if len(text.encode()) > 5_000_000:
            raise ValueError("Catalog exceeds 5 MB")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError("Catalog headers must match the exported CSV template")
        records, keys = [], set()
        for i, row in enumerate(reader, 2):
            if i > 10001:
                raise ValueError("Catalog exceeds 10,000 rows")
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Malformed CSV row {i}")
            if not row["sku"] or len(row["sku"]) > 100 or row["sku"] in keys:
                raise ValueError(f"Missing or duplicate SKU on row {i}")
            for key in ("sku", "supplier", "material", "currency", "rating_conditions", "retrieved_date"):
                if row[key].lstrip().startswith(("=", "+", "-", "@")):
                    raise ValueError(f"Spreadsheet formula prefix is not allowed in {key} on row {i}")
            if row["family"] not in ("spur", "helical", "bevel", "worm", "ring"):
                raise ValueError(f"Unsupported gear family on row {i}")
            for k, lo, hi in [
                ("module_mm", 0.1, 20), ("teeth", 6, 1000), ("pressure_deg", 14, 30),
                ("helix_deg", -45, 45), ("width_mm", 1, 500), ("bore_mm", 1, 500),
                ("hub_diameter_mm", 0, 1000), ("hub_width_mm", 0, 500),
                ("bending_nm", 0, 1e7), ("contact_nm", 0, 1e7),
            ]:
                row[k] = finite(row[k], f"{k} (row {i})", lo, hi)
            if not float(row["teeth"]).is_integer():
                raise ValueError(f"Teeth must be an integer on row {i}")
            row["teeth"] = int(row["teeth"])
            if row["family"] == "spur" and row["helix_deg"]:
                raise ValueError(f"Spur gears must have zero helix on row {i}")
            if row["source_url"]:
                url = urlsplit(row["source_url"])
                if (url.scheme != "https" or not url.hostname or url.username or url.password
                        or any(ch.isspace() or ord(ch)<32 for ch in row["source_url"])):
                    raise ValueError(f"Source URL must be a valid HTTPS URL without credentials on row {i}")
            if row["hub_diameter_mm"] and row["hub_diameter_mm"] <= row["bore_mm"]:
                raise ValueError(f"Hub must be wider than bore on row {i}")
            if any(len(str(v)) > 8000 for v in row.values()):
                raise ValueError(f"Field too long on row {i}")
            row["price"] = None if not row["price"].strip() else finite(row["price"], "price", 0, 1e7)
            keys.add(row["sku"])
            records.append(row)
        with self.connection:
            self.connection.executemany("INSERT INTO gears VALUES (?,?,?,?) ON CONFLICT(sku) DO UPDATE SET supplier=excluded.supplier,family=excluded.family,data=excluded.data",
                [(r["sku"], r["supplier"], r["family"], json.dumps(r, allow_nan=False)) for r in records])
        return len(records)

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(self.rows())
        return output.getvalue()

    def save_profile(self, profile):
        from dataclasses import asdict
        profile.validate()
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO profiles VALUES (?,?)", (profile.name, json.dumps(asdict(profile))))

    def profiles(self):
        from .models import PrintProfile
        return [PrintProfile(**json.loads(r[0])) for r in self.connection.execute("SELECT data FROM profiles ORDER BY name")]


# Generic dimensional choices. Ratings below are conservative screening assumptions,
# not attributed to a bearing manufacturer. The report explicitly states this.
BEARINGS = [
    {"sku": "608", "bore": 8., "outer": 22., "width": 7., "dynamic_n": 3000., "static_n": 1200., "speed_rpm": 20000.},
    {"sku": "6000", "bore": 10., "outer": 26., "width": 8., "dynamic_n": 4000., "static_n": 1800., "speed_rpm": 18000.},
    {"sku": "6001", "bore": 12., "outer": 28., "width": 8., "dynamic_n": 4500., "static_n": 2000., "speed_rpm": 16000.},
    {"sku": "6002", "bore": 15., "outer": 32., "width": 9., "dynamic_n": 5000., "static_n": 2500., "speed_rpm": 14000.},
    {"sku": "6003", "bore": 17., "outer": 35., "width": 10., "dynamic_n": 5500., "static_n": 3000., "speed_rpm": 12000.},
    {"sku": "6004", "bore": 20., "outer": 42., "width": 12., "dynamic_n": 8000., "static_n": 4000., "speed_rpm": 10000.},
    {"sku": "6005", "bore": 25., "outer": 47., "width": 12., "dynamic_n": 9000., "static_n": 5000., "speed_rpm": 8000.},
    {"sku": "6006", "bore": 30., "outer": 55., "width": 13., "dynamic_n": 10000., "static_n": 6000., "speed_rpm": 7000.},
    {"sku": "6008", "bore": 40., "outer": 68., "width": 15., "dynamic_n": 12000., "static_n": 8000., "speed_rpm": 5000.},
    {"sku": "6010", "bore": 50., "outer": 80., "width": 16., "dynamic_n": 14000., "static_n": 10000., "speed_rpm": 4000.},
]
