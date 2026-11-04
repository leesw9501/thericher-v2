"""Pure RAW OPEN-e/e+3 relative-sign weights for the native Paper account loop.

Consumes the existing source-attested forecast parser's result, not raw bytes.
Produces ModelPaperWeightsInput, never broker admission or absolute-profit claims.
"""

import math
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.research import model_paper_weights as weights

CHECKPOINT = "9364b09d7858f7bd08d373495697c359db25e788f594b4d1e8368ea34382153c"
TARGET = "OPEN_e_to_OPEN_e_plus_3_excess_EW17_not_operational_inclusive3"
UNITS = "simple_return_excess_vs_same_date_EW17"
POLICY = "raw-open-elapsed3-positive-equal-entry-native-timed-exit-v1"


def rows_from_forecast(parsed):
    """Unavailable is None, never replacement all-cash or reservation release."""
    try:
        if (type(parsed) is not dict
                or parsed["schema"] != "RAW_TCN_NONBROKER_SCORE_PROPOSAL_V1"
                or parsed["model_checkpoint_sha256"] != CHECKPOINT
                or parsed["forecast_horizon"] != TARGET
                or parsed["model_input_status"] != "ready"
                or parsed["inference_status"] != "scores_available"):
            return None
        rows = parsed["score_rows"]
        if type(rows) is not list or len(rows) != 17:
            return None
        selected = []
        routes = weights.MODEL_PAPER_US_CASH_H3_OPS_ROUTES[:17]
        for slot, (row, route) in enumerate(zip(rows, routes, strict=True)):
            if type(row) is not dict:
                return None
            score = row["expected_excess_return_open_e_to_open_e_plus_3"]
            if (type(row["slot"]) is not int or row["slot"] != slot or row["route"] != route
                    or row["symbol"] != route.split("/")[0]
                    or row["score_units"] != UNITS or row["model_score_known"] is not True
                    or type(score) is not float or not math.isfinite(score)):
                return None
            selected.append(score > 0)
        count = sum(selected)
        amount = 0.0 if count == 0 else 1.0 / count
        # Preserve equal selected weights without exceeding exact decimal mass.
        if count and Fraction(Decimal(repr(amount))) * count > 1:
            amount = math.nextafter(amount, 0.0)
        weight = Decimal(repr(amount))
        stock = tuple(
            weights.ModelPaperWeightRow(i, route, True, weight if positive else Decimal(0))
            for i, (route, positive) in enumerate(zip(routes, selected, strict=True))
        )
        return weights.append_derived_cash_h3_row(stock)
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return None


def prepare_raw_open_proposal(parsed, native_scores, metadata, *, entry_session, exit_session):
    """Bind causal native forecast clocks before using the unchanged weight codec.

    The caller still owns full source/input/hash attestation. This pure boundary
    cannot attest custody, infer a model, reconcile a request or release money.
    """
    rows = rows_from_forecast(parsed)
    if rows is None:
        return None
    try:
        observed = require_utc(datetime.fromisoformat(parsed["inference_observed_at"]))
        if type(metadata) is not weights.ModelPaperWeightsMetadata:
            return None
        metadata.__post_init__()
        if (metadata.model_ref != "sha256:" + CHECKPOINT
                or not metadata.inference_started_at <= observed <= metadata.inference_completed_at
                or type(native_scores) is not tuple or len(native_scores) != 17):
            return None
        for p, row in zip(native_scores, rows[:17], strict=True):
            if (type(p) is not TargetExposureProposal or p.symbol != row.route.split("/")[0]
                    or p.market != "US" or p.action != "abstain" or p.input_status != "ready"
                    or p.target_exposure != 0 or p.confidence != 0
                    or p.feature_window_end != metadata.feature_window_end
                    or p.feature_schema_id != metadata.feature_schema_id
                    or p.decided_at != observed or p.valid_until != observed):
                return None
        updated = replace(
            metadata, rows=rows, feature_mask_ref=weights.model_weight_mask_ref(rows),
            weight_bytes_ref=weights.model_weight_bytes_ref(rows),
        )
        return weights.prepare_model_paper_weights_input(
            updated, entry_session=entry_session, exit_session=exit_session,
            profile=weights.MODEL_PAPER_WEIGHTS_US_CASH_RAW_OPEN_ELAPSED3_PROFILE,
        )
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        return None
