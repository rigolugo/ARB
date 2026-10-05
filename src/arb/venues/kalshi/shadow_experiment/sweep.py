"""Phase B: offline sweep over one sanitized snapshot.  Pure; reproducible from
``LIVE_READ_SNAPSHOT_SANITIZED.json`` plus the effective configuration's
``shadow_experiment`` values (``trial_g`` label and ``minimum_spread_usd``
list, in configured order).  No winner is chosen."""

from __future__ import annotations

from decimal import Decimal

from . import constants as C
from . import shadow_evaluator as EV
from .config import ExperimentConfigV1
from .live_capture import inventory_from_snapshot


def _price_ranges(runner, raw):
    try:
        return runner._parse_price_ranges(raw), None
    except runner.RunnerError as exc:
        return None, exc.code.value


def run_sweep(mods: dict, cfg: ExperimentConfigV1, snapshot: dict) -> dict:
    mm, risk, runner = mods["mm"], mods["risk"], mods["runner"]
    spreads = cfg.shadow_experiment.minimum_spread_usd
    trial_g = cfg.shadow_experiment.trial_g
    ranges, grid_error = _price_ranges(runner, snapshot["market"].get("price_ranges"))
    book = snapshot["orderbook"]
    yes = [(Decimal(p), Decimal(q)) for p, q in book["yes_dollars_ascending"]]
    no = [(Decimal(p), Decimal(q)) for p, q in book["no_dollars_ascending"]]
    inventory = inventory_from_snapshot(EV, snapshot)
    rows = []
    for spread in spreads:
        obs = EV.evaluate_shadow(
            mm, risk, market_ticker=snapshot["market_ticker"], minimum_spread_usd=spread,
            yes_levels_ascending=yes, no_levels_ascending=no,
            price_ranges=ranges if ranges is not None else (),
            inventory=inventory, captured_book_identity=book["book_identity_sha256"],
            captured_at_utc=snapshot["captured_at_utc"], trial_G=trial_g,
            trial_G_authority=C.TRIAL_G_AUTHORITY, deviation_cap=None)
        rows.append(obs.to_dict())
    geometry_ok = all(r["best_yes_bid"] is not None for r in rows) and ranges is not None and book.get("parse_ok")
    if not geometry_ok:
        terminal = "SHADOW_EVALUATION_BINDING_UNAVAILABLE"
    elif inventory.state == EV.INVENTORY_UNKNOWN:
        terminal = "SHADOW_INPUT_UNKNOWN"
    else:
        terminal = "SHADOW_EXPERIMENT_COMPLETE"
    return {"schema": "ShadowExperimentMatrixV1", "authority": EV.AUTHORITY, "run_id": cfg.run_id,
            "selection_authority": C.SHADOW_ONLY_AUTHORITY,
            "trial_G": trial_g, "trial_G_authority": C.TRIAL_G_AUTHORITY,
            "canonical_G_selection": C.CANONICAL_G_SELECTION,
            "minimum_spread_matrix": [format(s, "f") for s in spreads],
            "minimum_spread_authority": C.MINIMUM_SPREAD_AUTHORITY, "winner_selected": False,
            "price_grid_error": grid_error, "rows": rows, "terminal": terminal}


CSV_COLUMNS = (
    "market_ticker", "trial_G", "minimum_spread_usd", "captured_book_identity", "captured_at_utc",
    "best_yes_bid", "best_yes_ask", "reference_yes_price", "observed_top_spread",
    "geometry_lower_candidate_assuming_flat_absent", "geometry_upper_candidate_assuming_flat_absent",
    "shadow_lower_candidate", "shadow_upper_candidate", "quantity", "inventory_observation",
    "working_order_observation", "suppression_reason_codes", "projected_lower_side_exposure_usd",
    "projected_upper_side_exposure_usd", "projected_target_working_exposure_usd", "price_reasonability",
)


def matrix_csv(matrix: dict) -> str:
    import csv
    import io
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in matrix["rows"]:
        writer.writerow(["|".join(row[c]) if isinstance(row[c], list) else ("UNKNOWN" if row[c] is None and c in (
            "best_yes_bid", "best_yes_ask") else ("NONE" if row[c] is None else row[c])) for c in CSV_COLUMNS])
    return out.getvalue()
