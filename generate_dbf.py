#!/usr/bin/env python3
"""Genereaza fisiere DBF din rapoarte XML de Trezorerie (Executie Angajamente
bugetare / BI Publisher), pe baza mapajului de taguri din "mapare taguri.xlsx".

Rulare:
    python3 generate_dbf.py [config.toml]

Daca nu se da niciun argument, se foloseste `config.toml` din folderul scriptului.
Nu are dependinte externe (isi scrie singur DBF-ul).
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_GLOB = "*.xml"

# --- Maparea tag XML -> camp DBF (din "mapare taguri.xlsx") ----------------
TAG_MAP = {
    "COD_FUNCTIONAL": "CAPITOL",
    "DENUMIRE_INDICATOR_CF": "DENCAP",
    "COD_ECONOMIC": "ARTICOL",
    "DENUMIRE_INDICATOR_CE": "DENART",
    "CA_DEF_AN_0_BUG": "CA_BUGET",
    "LIMITA_CA_AN_0_BUG": "CA_LIMITA",
    "CB_DEF_AN_0_BUG": "CB_BUGET",
    "CA_INI_AN_0": "CA_INI_AN",
    "CB_INI_AN_0": "CB_INI_AN",
    "CA_DEF_AN_0": "CA_DEF_AN",
    "CB_DEF_AN_0": "CB_DEF_AN",
    "CA_DISP": "CA_DISP",
    "CB_DISP": "CB_DISP",
    "RECEPTII": "RECEPTII",
    "PLATI_TREZ": "PL_TREZ",
    "PLATI_NTREZ": "PL_NTREZ",
    "REC_NEPL": "REC_NEPL",
    "SURSA_FINANTARE": "SURSA",
}

# --- Structura fisierului DBF tinta (identica cu forex.dbf de referinta) ---
# (nume_camp, tip, lungime, decimale)
DBF_FIELDS = [
    ("SURSA", "C", 20, 0),
    ("CAPITOL", "C", 6, 0),
    ("DENCAP", "C", 48, 0),
    ("ARTICOL", "C", 6, 0),
    ("DENART", "C", 78, 0),
    ("CA_BUGET", "N", 10, 2),
    ("CA_LIMITA", "N", 11, 2),
    ("CB_BUGET", "N", 10, 2),
    ("CA_INI_AN", "N", 8, 2),
    ("CB_INI_AN", "N", 8, 2),
    ("CA_DEF_AN", "N", 11, 2),
    ("CB_DEF_AN", "N", 12, 2),
    ("CA_DISP", "N", 10, 2),
    ("CB_DISP", "N", 10, 2),
    ("RECEPTII", "N", 11, 2),
    ("PL_TREZ", "N", 11, 2),
    ("PL_NTREZ", "N", 7, 2),
    ("REC_NEPL", "N", 8, 2),
]

ENCODING = "cp1252"  # ASCII-compatibil; textele din aceste rapoarte nu au diacritice
LANGUAGE_DRIVER_ID = 0x01  # codepage 437, ca in forex.dbf original


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class Config:
    def __init__(self, input_folders: list[Path], output_folder: Path, glob_pattern: str) -> None:
        self.input_folders = input_folders
        self.output_folder = output_folder
        self.glob_pattern = glob_pattern


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise SystemExit(f"Nu am gasit fisierul de config: {path}")

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    raw_inputs = data.get("input_folders")
    if not raw_inputs or not isinstance(raw_inputs, list):
        raise SystemExit("Config invalid: 'input_folders' trebuie sa fie o lista nevida.")

    raw_output = data.get("output_folder")
    if not raw_output or not isinstance(raw_output, str):
        raise SystemExit("Config invalid: 'output_folder' trebuie setat (string).")

    return Config(
        input_folders=[Path(p).expanduser() for p in raw_inputs],
        output_folder=Path(raw_output).expanduser(),
        glob_pattern=data.get("glob_pattern", DEFAULT_GLOB),
    )


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", name.strip())
    return cleaned.strip("_") or "output"


# ---------------------------------------------------------------------------
# Parsare XML
# ---------------------------------------------------------------------------

def parse_xml_records(xml_path: Path) -> list[dict[str, str]]:
    """Extrage randurile de detaliu dintr-un raport XML de Trezorerie.

    Raportul (DATA_DS) contine mai multe grupuri <G_4><NIVEL>n</NIVEL>...</G_4>:
    - NIVEL 0: doar un contor total de randuri (<CONTOR>), fara detaliu -
      folosit aici doar ca verificare.
    - NIVEL 1, 2, ...: cate un set complet de randuri <G_11> (unele cu
      COD_ECONOMIC = randuri de detaliu, altele TOTAL/subtotal fara el).
      In fisierele vazute, aceste seturi sunt duplicate identice ale
      aceleiasi date -> se foloseste doar PRIMUL grup care are randuri
      de detaliu, restul sunt ignorate.
    """
    root = ET.parse(xml_path).getroot()

    contor = None
    detail_g11s = None
    for g4 in root.findall("G_4"):
        nivel_el = g4.find("NIVEL")
        g11s = g4.findall(".//G_11")
        rows_with_detail = [g11 for g11 in g11s if g11.find("COD_ECONOMIC") is not None]

        if not rows_with_detail:
            contor_el = g4.find(".//CONTOR")
            if nivel_el is not None and nivel_el.text == "0" and contor_el is not None and contor_el.text:
                contor = int(contor_el.text)
            continue

        if detail_g11s is None:
            detail_g11s = rows_with_detail

    if detail_g11s is None:
        raise ValueError("nu s-au gasit randuri de detaliu (cu COD_ECONOMIC)")

    if contor is not None and contor != len(detail_g11s):
        print(
            f"    ATENTIE: raportul declara CONTOR={contor} randuri, "
            f"dar primul grup de detaliu are {len(detail_g11s)} randuri.",
            file=sys.stderr,
        )

    records = []
    for g11 in detail_g11s:
        record = {}
        for xml_tag, dbf_field in TAG_MAP.items():
            el = g11.find(xml_tag)
            record[dbf_field] = (el.text or "").strip() if el is not None and el.text else ""
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# Scriere DBF
# ---------------------------------------------------------------------------

class FieldOverflow(Exception):
    """Valoarea numerica nu incape in latimea fixa a campului DBF."""


def format_field(value: str, ftype: str, length: int, decimals: int) -> str:
    if ftype == "C":
        return str(value)[:length].ljust(length)
    elif ftype == "N":
        try:
            num = float(value) if value not in (None, "") else 0.0
        except ValueError:
            num = 0.0
        text = f"{num:.{decimals}f}"
        if len(text) > length:
            raise FieldOverflow(text)
        return text.rjust(length)
    else:
        raise ValueError(f"Tip de camp necunoscut: {ftype}")


def write_dbf(records: list[dict[str, str]], out_path: Path, fields=DBF_FIELDS, encoding: str = ENCODING) -> None:
    """Scrie fisierul DBF. Daca o valoare numerica nu incape in latimea
    fixa a campului (ex. sume peste 99999.99 intr-un camp N(8,2)), campul
    este lasat GOL (spatii) in loc de trunchiat/rotunjit - acelasi
    comportament observat in forex.dbf de referinta - si se raporteaza un
    avertisment, ca sa nu treaca neobservata o pierdere de date."""
    field_count = len(fields)
    header_size = 32 + 32 * field_count + 1
    record_size = 1 + sum(f[2] for f in fields)
    n_records = len(records)

    today = date.today()
    header = bytearray(32)
    header[0] = 0x03  # dBASE III, fara memo
    header[1] = today.year - 1900
    header[2] = today.month
    header[3] = today.day
    header[4:8] = n_records.to_bytes(4, "little")
    header[8:10] = header_size.to_bytes(2, "little")
    header[10:12] = record_size.to_bytes(2, "little")
    header[29] = LANGUAGE_DRIVER_ID

    field_descriptors = bytearray()
    for name, ftype, length, decimals in fields:
        name_bytes = name.encode("ascii")[:10].ljust(11, b"\x00")
        desc = bytearray(32)
        desc[0:11] = name_bytes
        desc[11] = ord(ftype)
        desc[16] = length
        desc[17] = decimals
        field_descriptors += desc

    overflow_warnings = []
    with out_path.open("wb") as f:
        f.write(header)
        f.write(field_descriptors)
        f.write(b"\x0d")  # terminator header
        for rec_index, rec in enumerate(records):
            f.write(b" ")  # flag de stergere (spatiu = nesters)
            for name, ftype, length, decimals in fields:
                value = rec.get(name, "")
                try:
                    text = format_field(value, ftype, length, decimals)
                except FieldOverflow as exc:
                    text = " " * length
                    where = rec.get("ARTICOL") or rec.get("CAPITOL") or f"rand {rec_index + 1}"
                    overflow_warnings.append(
                        f"rand {rec_index + 1} ({where}): {name}={exc} nu incape in {length} caractere -> lasat gol"
                    )
                f.write(text.encode(encoding, errors="replace"))
        f.write(b"\x1a")  # EOF

    if overflow_warnings:
        print(f"    ATENTIE: {len(overflow_warnings)} valoare(i) lasate goale (nu incapeau in DBF):", file=sys.stderr)
        for w in overflow_warnings:
            print(f"      {w}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Procesare per folder
# ---------------------------------------------------------------------------

def process_folder(input_folder: Path, output_base: Path, config: Config) -> bool:
    print(f"\n=== Folder: {input_folder} ===")
    if not input_folder.is_dir():
        print(f"  EROARE: folderul nu exista, il sar.", file=sys.stderr)
        return False

    xml_files = sorted(input_folder.glob(config.glob_pattern))
    if not xml_files:
        print(f"  Nu am gasit fisiere XML ({config.glob_pattern}), il sar.", file=sys.stderr)
        return False

    out_dir = output_base / sanitize_name(input_folder.name)
    out_dir.mkdir(parents=True, exist_ok=True)

    failed: list[tuple[str, str]] = []
    ok_count = 0
    for xml_path in xml_files:
        try:
            records = parse_xml_records(xml_path)
            out_path = out_dir / f"{xml_path.stem}.dbf"
            write_dbf(records, out_path)
            print(f"  OK: {xml_path.name} -> {out_path.name} ({len(records)} randuri)")
            ok_count += 1
        except Exception as exc:  # noqa: BLE001 - vrem sa continuam batch-ul
            failed.append((xml_path.name, str(exc)))
            print(f"  ESUAT: {xml_path.name}: {exc}", file=sys.stderr)

    print(f"  Fisiere XML gasite: {len(xml_files)} | procesate: {ok_count} | esuate: {len(failed)}")
    if failed:
        print(f"  Fisiere esuate:")
        for name, reason in failed:
            print(f"    - {name}: {reason}")

    return len(failed) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Genereaza fisiere DBF din rapoarte XML de Trezorerie.")
    parser.add_argument(
        "config",
        nargs="?",
        default=str(Path(__file__).resolve().parent / "config.toml"),
        help="Calea catre fisierul de config TOML (default: config.toml langa script).",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config).expanduser())
    config.output_folder.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for input_folder in config.input_folders:
        ok = process_folder(input_folder, config.output_folder, config)
        all_ok = all_ok and ok

    print(f"\nGata. Output in: {config.output_folder}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
