"""
report_engine.py
OOH Campaign Report Engine

Ports the Google Apps Script OOH Automation logic to Python.
Input : campaign_id  +  SQLAlchemy Session
Output: structured dict with DTD detail, KPIs, publisher & inventory breakdowns.

Classification rules (mirrors the JS script):
  - Programmatic : record has billed_impressions > 0  OR  billed_ad_play > 0  OR  spent > 0
  - Traditional  : cumulative RDS data (no billed fields); distributed evenly
                   across campaign days up to the upload date.
"""

import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from database import Campaign, OOHInventory, Performance


# ─────────────────────────────────────────────────────────────────────────────
#  String utilities  (mirrors JS: norm / superNorm / tokenize)
# ─────────────────────────────────────────────────────────────────────────────

def _norm(val) -> str:
    if val is None:
        return ""
    s = unicodedata.normalize("NFD", str(val))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _super_norm(val) -> str:
    if not val:
        return ""
    s = unicodedata.normalize("NFD", str(val))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


_STOP_WORDS = {"clone", "copia", "pantalla", "valla", "digital", "unid", "unit", "ooh", "dooh", "db"}


def _tokenize(val) -> set:
    return {w for w in _norm(val).split() if len(w) > 2 and w not in _STOP_WORDS}


def _strip_db_suffix(val: str) -> str:
    """Remove trailing ' - DB' or '(DB)' variants."""
    s = re.sub(r"\s*\(DB\)\s*$", "", val, flags=re.IGNORECASE)
    s = re.sub(r"\s*[-–]\s*DB\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _is_junk(val) -> bool:
    s = _super_norm(val or "")
    return not s or any(x in s for x in ("total", "grandtotal", "nota", "campaign"))


# ─────────────────────────────────────────────────────────────────────────────
#  Master plan builder  (mirrors JS planList)
# ─────────────────────────────────────────────────────────────────────────────

def _build_master_plan(inventories: list) -> list[dict]:
    plan = []
    for inv in inventories:
        name = str(inv.name or "")
        billboard = str(inv.billboard_name or name)
        city = str(inv.location or "N/A")
        publisher = str(inv.media_owner or "RDS Multimidia")
        cpm = float(inv.ecpm_mxn or 0)
        plan.append({
            "name": name,
            "billboard_name": billboard,
            "publisher": publisher,
            "city": city,
            "cpm": cpm,
            "ooh_impressions_planned": float(inv.ooh_impressions or 0),
            "search_tokens": _tokenize(f"{name} {billboard} {city}"),
            "_sn": _super_norm(name),
            "_sb": _super_norm(billboard),
        })
    return plan


# ─────────────────────────────────────────────────────────────────────────────
#  Fuzzy inventory matching  (mirrors JS findBestMatchByDistrict)
# ─────────────────────────────────────────────────────────────────────────────

def _find_best_match(inventory_name: Optional[str], master_plan: list) -> Optional[dict]:
    if not inventory_name or not master_plan:
        return None

    clean = _strip_db_suffix(inventory_name)
    sn_rep = _super_norm(clean)
    tokens_rep = _tokenize(clean)

    best_score = 0
    best_match = None

    for plan in master_plan:
        # Exact match → return immediately
        if sn_rep and (sn_rep == plan["_sn"] or sn_rep == plan["_sb"]):
            return plan

        score = 0
        if plan["_sn"] and (plan["_sn"] in sn_rep or sn_rep in plan["_sn"]):
            score += 15
        if plan["_sb"] and (plan["_sb"] in sn_rep or sn_rep in plan["_sb"]):
            score += 15
        score += len(tokens_rep & plan["search_tokens"]) * 10

        if score > best_score:
            best_score = score
            best_match = plan

    return best_match if best_score >= 10 else None


# ─────────────────────────────────────────────────────────────────────────────
#  Record classification  (mirrors JS isProgrammatic logic)
# ─────────────────────────────────────────────────────────────────────────────

def _is_programmatic(perf: Performance) -> bool:
    fname = (perf.file_name or "").rsplit(".", 1)[0].strip()
    if re.fullmatch(r"\d+", fname):
        return False
    return bool(
        (perf.billed_impressions is not None and float(perf.billed_impressions) > 0)
        or (perf.billed_ad_play is not None and float(perf.billed_ad_play) > 0)
        or (perf.spent is not None and float(perf.spent) > 0)
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Row expansion
# ─────────────────────────────────────────────────────────────────────────────

def _expand_traditional(perf: Performance, campaign: Campaign, master_plan: list) -> list[dict]:
    """
    Traditional (RDS) records carry cumulative totals with no meaningful date.
    Distributes evenly: total / diff_days → one row per day.
    Spend = (impressions * CPM) / 1000  using the plan CPM when available.
    """
    camp_start: date = campaign.start_date or date.today()
    camp_end: date = campaign.end_date or date.today()

    file_date: date = perf.uploaded_at.date() if perf.uploaded_at else date.today()
    real_end = min(file_date, camp_end)

    diff_days = max((real_end - camp_start).days + 1, 1)

    total_imp = float(perf.ooh_impressions or 0)
    total_adp = float(perf.ad_plays or 0)

    match = _find_best_match(perf.inventory, master_plan)
    cpm = match["cpm"] if match else 0
    publisher = match["publisher"] if match else (perf.publisher or "RDS Multimidia")

    total_spend = (total_imp * cpm / 1000) if cpm > 0 else float(perf.media_cost or 0)

    daily_imp = total_imp / diff_days
    daily_adp = total_adp / diff_days
    daily_spend = total_spend / diff_days
    inv_name = _strip_db_suffix(perf.inventory or "Unknown")

    rows = []
    for d in range(diff_days):
        rows.append({
            "date": camp_start + timedelta(days=d),
            "inventory": inv_name,
            "publisher": publisher,
            "ad_plays": round(daily_adp, 2),
            "impressions": round(daily_imp, 2),
            "spend": round(daily_spend, 4),
            "source": "traditional",
        })
    return rows


def _expand_programmatic(perf: Performance) -> list[dict]:
    """
    Programmatic records are already daily; mapped directly.
    Prefers billed fields over raw fields (mirrors JS colAdP / colImp / colSpent).
    """
    inv_name = _strip_db_suffix(perf.inventory or "Unknown")
    return [{
        "date": perf.date,
        "inventory": inv_name,
        "publisher": perf.publisher or "Programmatic",
        "ad_plays": round(float(perf.billed_ad_play or perf.ad_plays or 0), 2),
        "impressions": round(float(perf.billed_impressions or perf.ooh_impressions or 0), 2),
        "spend": round(float(perf.spent or perf.media_cost or 0), 4),
        "source": "programmatic",
    }]


# ─────────────────────────────────────────────────────────────────────────────
#  KPI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(val).split("-")[0])
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _calculate_kpis(dtd_df: pd.DataFrame, campaign: Campaign) -> dict:
    total_impressions = float(dtd_df["impressions"].sum()) if not dtd_df.empty else 0.0
    total_ad_plays = float(dtd_df["ad_plays"].sum()) if not dtd_df.empty else 0.0
    total_spend = float(dtd_df["spend"].sum()) if not dtd_df.empty else 0.0
    real_ecpm = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0.0

    planned_imp = _safe_float(campaign.total_ooh_impressions_planned)
    planned_adp = _safe_float(campaign.ad_plays_planned)
    planned_budget = _safe_float(campaign.total_cost_ooh) or _safe_float(campaign.net_cost)
    planned_ecpm = _safe_float(campaign.ecpm_mxn_planned)
    if planned_ecpm == 0 and planned_imp > 0 and planned_budget > 0:
        planned_ecpm = (planned_budget / planned_imp) * 1000

    return {
        # Actuals
        "total_impressions": total_impressions,
        "total_ad_plays": total_ad_plays,
        "total_spend": total_spend,
        "real_ecpm": real_ecpm,
        # Plan targets
        "planned_impressions": planned_imp,
        "planned_ad_plays": planned_adp,
        "planned_budget": planned_budget,
        "planned_ecpm": planned_ecpm,
        # Delivery %
        "pct_impressions": total_impressions / planned_imp if planned_imp > 0 else 0.0,
        "pct_ad_plays": total_ad_plays / planned_adp if planned_adp > 0 else 0.0,
        "pct_spend": total_spend / planned_budget if planned_budget > 0 else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_campaign_report(campaign_id: str, db: Session) -> Optional[dict]:
    """
    Generates a full delivery report for any campaign_id.

    Returns
    -------
    dict with keys:
        campaign        : Campaign ORM object
        dtd_df          : DataFrame  [date, inventory, publisher, ad_plays, impressions, spend, source]
        kpis            : dict       planned vs actual metrics + delivery %
        publisher_df    : DataFrame  [publisher, ad_plays, impressions, spend, sov_pct]
        daily_df        : DataFrame  [date, ad_plays, impressions, spend]  — timeline totals
        inventory_df    : DataFrame  [inventory, publisher, ad_plays, impressions, spend]
    Returns None if campaign_id does not exist.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return None

    inventories = (
        db.query(OOHInventory)
        .filter(OOHInventory.campaign_id == campaign_id)
        .all()
    )
    master_plan = _build_master_plan(inventories)

    performances = (
        db.query(Performance)
        .filter(Performance.campaign_id == campaign_id)
        .all()
    )

    # ── Deduplicate traditional records by (file_name, inventory) ────────────
    # mirrors JS seenNames — avoids double-counting repeated inventory rows
    seen_traditional: set = set()
    raw_rows: list[dict] = []

    for perf in performances:
        if _is_programmatic(perf):
            raw_rows.extend(_expand_programmatic(perf))
        else:
            key = (perf.file_name or "", perf.inventory or "")
            if key in seen_traditional:
                continue
            seen_traditional.add(key)
            raw_rows.extend(_expand_traditional(perf, campaign, master_plan))

    # ── Empty campaign guard ─────────────────────────────────────────────────
    empty_result = {
        "campaign": campaign,
        "dtd_df": pd.DataFrame(),
        "kpis": _calculate_kpis(pd.DataFrame(), campaign),
        "publisher_df": pd.DataFrame(),
        "daily_df": pd.DataFrame(),
        "inventory_df": pd.DataFrame(),
    }
    if not raw_rows:
        return empty_result

    # ── Aggregate DTD: same (date, inventory, publisher) → sum ───────────────
    df = pd.DataFrame(raw_rows)
    dtd_df = (
        df.groupby(["date", "inventory", "publisher", "source"], as_index=False)
        .agg(
            ad_plays=("ad_plays", "sum"),
            impressions=("impressions", "sum"),
            spend=("spend", "sum"),
        )
        .sort_values(["date", "inventory"])
        .reset_index(drop=True)
    )
    dtd_df["ad_plays"] = dtd_df["ad_plays"].round(2)
    dtd_df["impressions"] = dtd_df["impressions"].round(2)
    dtd_df["spend"] = dtd_df["spend"].round(4)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpis = _calculate_kpis(dtd_df, campaign)

    # ── Publisher breakdown ───────────────────────────────────────────────────
    publisher_df = (
        dtd_df.groupby("publisher", as_index=False)
        .agg(
            ad_plays=("ad_plays", "sum"),
            impressions=("impressions", "sum"),
            spend=("spend", "sum"),
        )
        .sort_values("impressions", ascending=False)
        .reset_index(drop=True)
    )
    total_imp = kpis["total_impressions"]
    publisher_df["sov_pct"] = (
        publisher_df["impressions"] / total_imp if total_imp > 0 else 0.0
    )

    # ── Daily totals timeline ─────────────────────────────────────────────────
    daily_df = (
        dtd_df.groupby("date", as_index=False)
        .agg(
            ad_plays=("ad_plays", "sum"),
            impressions=("impressions", "sum"),
            spend=("spend", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    # ── Per-inventory summary ─────────────────────────────────────────────────
    inventory_df = (
        dtd_df.groupby(["inventory", "publisher"], as_index=False)
        .agg(
            ad_plays=("ad_plays", "sum"),
            impressions=("impressions", "sum"),
            spend=("spend", "sum"),
        )
        .sort_values("impressions", ascending=False)
        .reset_index(drop=True)
    )

    return {
        "campaign": campaign,
        "dtd_df": dtd_df,
        "kpis": kpis,
        "publisher_df": publisher_df,
        "daily_df": daily_df,
        "inventory_df": inventory_df,
    }
