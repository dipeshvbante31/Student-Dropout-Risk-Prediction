"""CSV parsing + validation against the model's own feature schema (no second column list exists)."""
import csv
import io
import re

from ml.preprocess import clean_name

REF_RE = re.compile(r"^[A-Za-z0-9._\-/ ]{1,64}$")
FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def template_csv(predictor) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(["student_id"] + [s["name"] for s in predictor.schema])
    return buf.getvalue()


def safe_cell(v):
    """Neutralise spreadsheet formula injection on export."""
    if isinstance(v, str) and v.startswith(FORMULA_CHARS):
        return "'" + v
    return v


def parse_and_validate(data: bytes, predictor, max_rows: int) -> dict:
    """Policy: file-level problems (encoding, empty, header mismatch, too many rows) reject the whole file.
    Row-level problems reject only that row; rejected rows are reported with reasons and never predicted,
    modified or silently dropped."""
    out = {"file_errors": [], "rows": [], "rejected": [], "total": 0, "columns": []}
    if not data.strip():
        out["file_errors"].append("The file is empty.")
        return out
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        out["file_errors"].append("The file is not valid UTF-8 text. Re-save it as 'CSV UTF-8'.")
        return out
    if "\x00" in text:
        out["file_errors"].append("The file contains binary data and is not a CSV.")
        return out
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header_raw = next(reader)
    except (StopIteration, csv.Error):
        out["file_errors"].append("The file has no header row.")
        return out
    header = [clean_name(h) for h in header_raw]
    out["columns"] = header
    required = [s["name"] for s in predictor.schema]
    allowed = set(required) | {"student_id"}
    dup = sorted({h for h in header if header.count(h) > 1})
    if dup:
        out["file_errors"].append(f"Duplicate column(s): {', '.join(dup)}.")
    missing = [c for c in required if c not in header]
    unexpected = [h for h in header if h not in allowed]
    if missing:
        out["file_errors"].append(f"Missing required column(s): {', '.join(missing)}.")
    if unexpected:
        out["file_errors"].append(f"Unexpected column(s): {', '.join(unexpected)}. Remove them or use the template.")
    if out["file_errors"]:
        return out

    seen = set()
    try:
        for rec in reader:
            if reader.line_num - 1 > max_rows + 50 and out["total"] > max_rows:
                break
            out["total"] += 1
            row_no = out["total"]
            if out["total"] > max_rows:
                out["file_errors"].append(f"Too many rows: the limit is {max_rows} per upload.")
                out["rows"], out["rejected"] = [], []
                return out
            if not any(c.strip() for c in rec):
                out["rejected"].append({"row": row_no, "student_id": None, "errors": ["empty row"]})
                continue
            if len(rec) != len(header):
                out["rejected"].append({"row": row_no, "student_id": None,
                                        "errors": [f"expected {len(header)} columns, found {len(rec)}"]})
                continue
            raw = dict(zip(header, rec))
            ref = raw.get("student_id", "").strip() or None
            errs = []
            if ref is not None:
                if not REF_RE.match(ref):
                    errs.append("student_id: use 1-64 letters, digits, space or . _ - /")
                elif ref in seen:
                    errs.append(f"student_id: duplicate of an earlier row in this file")
                seen.add(ref)
            clean, verrs, warns = predictor.validate_record(raw)
            errs += verrs
            if errs:
                out["rejected"].append({"row": row_no, "student_id": ref if ref and REF_RE.match(ref) else None, "errors": errs})
            else:
                out["rows"].append({"row": row_no, "ref": ref, "features": clean, "warnings": warns})
    except csv.Error as exc:
        out["file_errors"].append(f"Malformed CSV near row {out['total'] + 1}: {exc}")
        return out
    if out["total"] == 0:
        out["file_errors"].append("The file has a header but no data rows.")
    elif not out["rows"]:
        out["file_errors"].append("No valid rows: every record failed validation (see details below).")
    return out
