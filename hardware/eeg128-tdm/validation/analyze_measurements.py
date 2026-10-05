#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class Limits:
    noise_rms_uv_max: float
    settling_error_uv_max: float
    cmrr_db_min: float
    crosstalk_db_max: float


def finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def require_channels(rows: list[dict[str, Any]], field: str) -> None:
    channels = {int(row["channel"]) for row in rows}
    expected = set(range(128))
    if channels != expected:
        missing = sorted(expected - channels)
        extra = sorted(channels - expected)
        raise ValueError(
            f"{field} must contain exactly channels 0..127; "
            f"missing={missing}, extra={extra}"
        )


def evaluate(data: dict[str, Any]) -> dict[str, Any]:
    limits_raw = data["limits"]
    limits = Limits(
        noise_rms_uv_max=finite(
            limits_raw["noise_rms_uv_max"], "noise_rms_uv_max"
        ),
        settling_error_uv_max=finite(
            limits_raw["settling_error_uv_max"], "settling_error_uv_max"
        ),
        cmrr_db_min=finite(limits_raw["cmrr_db_min"], "cmrr_db_min"),
        crosstalk_db_max=finite(
            limits_raw["crosstalk_db_max"], "crosstalk_db_max"
        ),
    )

    equipment = data.get("equipment", [])
    if not equipment:
        raise ValueError("at least one calibrated equipment record is required")
    uncalibrated = [
        item.get("id", "<unknown>")
        for item in equipment
        if not bool(item.get("calibration_valid", False))
    ]

    noise = list(data["noise"])
    settling = list(data["settling"])
    cmrr = list(data["cmrr"])
    crosstalk = list(data["crosstalk"])

    require_channels(noise, "noise")
    require_channels(settling, "settling")

    noise_values = [
        finite(row["rms_uv_0p5_100hz"], "noise.rms_uv_0p5_100hz")
        for row in noise
    ]
    settling_values = [
        finite(
            row["max_retained_error_uv"],
            "settling.max_retained_error_uv",
        )
        for row in settling
    ]
    cmrr_values = [
        finite(row["cmrr_db"], "cmrr.cmrr_db")
        for row in cmrr
        if float(row["frequency_hz"]) in (50.0, 60.0)
    ]
    crosstalk_values = [
        finite(row["coupling_db"], "crosstalk.coupling_db")
        for row in crosstalk
    ]

    if not cmrr_values:
        raise ValueError("CMRR data must include 50 Hz and/or 60 Hz measurements")
    if not crosstalk_values:
        raise ValueError("crosstalk measurements are required")

    drl = data["drl_stability"]
    external = data["external_safety_lab"]

    checks = {
        "equipment_calibration": not uncalibrated,
        "noise": max(noise_values) < limits.noise_rms_uv_max,
        "settling": max(settling_values) <= limits.settling_error_uv_max,
        "cmrr": min(cmrr_values) >= limits.cmrr_db_min,
        "crosstalk": max(crosstalk_values) <= limits.crosstalk_db_max,
        "drl_stability": bool(drl["pass"]),
        "external_safety_lab": bool(external["pass"])
        and bool(external.get("report_id")),
    }

    return {
        "schema_version": 1,
        "source": "physical bench measurements",
        "simulated": False,
        "checks": checks,
        "engineering_validation_passed": all(checks.values()),
        "statistics": {
            "noise_worst_rms_uv_0p5_100hz": max(noise_values),
            "noise_median_rms_uv_0p5_100hz": sorted(noise_values)[64],
            "settling_worst_retained_error_uv": max(settling_values),
            "cmrr_worst_db_50_60hz": min(cmrr_values),
            "crosstalk_worst_db": max(crosstalk_values),
        },
        "limits": {
            "noise_rms_uv_max": limits.noise_rms_uv_max,
            "settling_error_uv_max": limits.settling_error_uv_max,
            "cmrr_db_min": limits.cmrr_db_min,
            "crosstalk_db_max": limits.crosstalk_db_max,
        },
        "uncalibrated_equipment": uncalibrated,
        "external_safety_lab": {
            "report_id": external.get("report_id", ""),
            "scope": external.get("scope", ""),
            "pass": bool(external["pass"]),
        },
        "regulatory_note": (
            "Engineering validation is not IEC 60601 certification, FDA clearance, "
            "or EU MDR conformity assessment. The external report must be reviewed "
            "for the actual intended use and applicable standards."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("electrical-validation-result.json"),
    )
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate(data)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["engineering_validation_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
