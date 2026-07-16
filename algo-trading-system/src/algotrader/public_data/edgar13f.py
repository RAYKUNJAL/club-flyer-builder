"""Real 'top traders' data from SEC EDGAR 13F filings -- free, official, public.

Every institutional manager over $100M AUM must disclose long US equity
holdings quarterly on Form 13F. This module pulls the latest 13F-HR for a
curated list of well-known managers and condenses each into a leaderboard
entry: total disclosed portfolio value, filing date, and top holdings with
weights.

This is the honestly-accessible version of what copy-trading apps show. Know
its limits before treating it as a signal:
  * 13Fs are filed up to 45 days after quarter end -- always stale.
  * Long US equities/options only: no shorts, no futures, no cash, no
    international, so a filing is NOT the fund's full book.
  * Values are reported in whole dollars (post-Jan-2023 rule).

SEC fair-access rules: send a descriptive User-Agent with contact info and
stay well under 10 requests/second. We sleep between requests.

CIK numbers below were verified against live EDGAR (entity name + presence of
13F-HR filings) on 2026-07-16.
"""
from __future__ import annotations

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "algotrader-dashboard research contact: raykunjal@gmail.com"
REQUEST_GAP_SECONDS = 0.2

#: (cik, fund name, the manager people know it by)
FAMOUS_FUNDS: list[tuple[int, str, str]] = [
    (1067983, "Berkshire Hathaway", "Warren Buffett"),
    (1649339, "Scion Asset Management", "Michael Burry"),
    (1336528, "Pershing Square Capital", "Bill Ackman"),
    (1536411, "Duquesne Family Office", "Stanley Druckenmiller"),
    (1350694, "Bridgewater Associates", "Ray Dalio"),
    (1037389, "Renaissance Technologies", "Jim Simons (founder)"),
    (1656456, "Appaloosa", "David Tepper"),
    (1061768, "Baupost Group", "Seth Klarman"),
    (1040273, "Third Point", "Daniel Loeb"),
    (1079114, "Greenlight Capital", "David Einhorn"),
]

_13F_NS = "{http://www.sec.gov/edgar/document/thirteenf/informationtable}"


@dataclass
class FundSnapshot:
    cik: int
    fund: str
    manager: str
    filing_date: str
    total_value: float
    num_positions: int
    top_holdings: list[dict] = field(default_factory=list)  # {issuer, value, weight}
    reported_in_thousands: bool = False


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _latest_13f_accession(cik: int) -> tuple[str, str]:
    """Return (accession_no_dashes, filing_date) of the newest 13F-HR."""
    sub = _get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = sub["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "13F-HR":
            return recent["accessionNumber"][i].replace("-", ""), recent["filingDate"][i]
    raise LookupError(f"CIK {cik}: no 13F-HR filing found")


def _find_infotable_url(cik: int, accession: str) -> str:
    idx = _get_json(f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json")
    names = [item["name"] for item in idx["directory"]["item"]]
    xml_names = [n for n in names if n.lower().endswith(".xml")]
    # The holdings live in the "information table" XML; prefer an explicit name,
    # fall back to any XML that isn't the cover/primary document.
    for n in xml_names:
        if "infotable" in n.lower() or "info_table" in n.lower():
            return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{n}"
    for n in xml_names:
        if "primary" not in n.lower():
            return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{n}"
    raise LookupError(f"CIK {cik} accession {accession}: no information-table XML in filing index")


def parse_infotable(xml_bytes: bytes) -> list[dict]:
    """Parse a 13F information table into [{issuer, value}] rows (value in dollars)."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for it in root.iter(f"{_13F_NS}infoTable"):
        issuer_el = it.find(f"{_13F_NS}nameOfIssuer")
        value_el = it.find(f"{_13F_NS}value")
        if issuer_el is None or value_el is None or value_el.text is None:
            continue
        rows.append({"issuer": (issuer_el.text or "").strip(), "value": float(value_el.text)})
    return rows


def aggregate_holdings(rows: list[dict], top_n: int = 10) -> tuple[float, int, list[dict]]:
    """Merge duplicate issuers (multiple share classes / put-call lines), rank by value."""
    by_issuer: dict[str, float] = {}
    for r in rows:
        by_issuer[r["issuer"]] = by_issuer.get(r["issuer"], 0.0) + r["value"]
    total = sum(by_issuer.values())
    ranked = sorted(by_issuer.items(), key=lambda kv: kv[1], reverse=True)
    top = [
        {"issuer": issuer, "value": value, "weight": (value / total if total else 0.0)}
        for issuer, value in ranked[:top_n]
    ]
    return total, len(by_issuer), top


def fetch_fund_snapshot(cik: int, fund: str, manager: str) -> FundSnapshot:
    accession, filing_date = _latest_13f_accession(cik)
    time.sleep(REQUEST_GAP_SECONDS)
    info_url = _find_infotable_url(cik, accession)
    time.sleep(REQUEST_GAP_SECONDS)
    rows = parse_infotable(_get_bytes(info_url))
    total, n_positions, top = aggregate_holdings(rows)
    # Units correction: 13F values must be whole dollars since Jan 2023, but some
    # filers still submit in thousands (verified live: Baupost's 2026-05-14 filing
    # lists AMZN at "649543" = $649.5M). Because the 13F filing threshold is $100M
    # of 13F securities, a filing totaling under $100M is a units error, not a
    # small portfolio -- scale it up and flag it.
    reported_in_thousands = 0 < total < 100_000_000
    if reported_in_thousands:
        total *= 1000.0
        for h in top:
            h["value"] *= 1000.0
    return FundSnapshot(
        cik=cik, fund=fund, manager=manager, filing_date=filing_date,
        total_value=total, num_positions=n_positions, top_holdings=top,
        reported_in_thousands=reported_in_thousands,
    )


def fetch_all(funds: list[tuple[int, str, str]] | None = None) -> dict:
    """Fetch snapshots for every fund; per-fund failures are reported, not fatal."""
    funds = funds if funds is not None else FAMOUS_FUNDS
    snapshots, errors = [], []
    for cik, fund, manager in funds:
        try:
            snap = fetch_fund_snapshot(cik, fund, manager)
            snapshots.append(snap.__dict__)
        except Exception as exc:  # noqa: BLE001 -- keep the leaderboard partial, not broken
            errors.append({"cik": cik, "fund": fund, "error": str(exc)})
        time.sleep(REQUEST_GAP_SECONDS)
    snapshots.sort(key=lambda s: s["total_value"], reverse=True)
    return {
        "source": "SEC EDGAR Form 13F-HR (official, public). Long US equity positions only; "
                  "filed up to 45 days after quarter end.",
        "funds": snapshots,
        "errors": errors,
    }


def write_snapshot_file(out_path: Path, funds: list[tuple[int, str, str]] | None = None) -> dict:
    from datetime import datetime, timezone

    data = fetch_all(funds)
    data["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2))
    return data
