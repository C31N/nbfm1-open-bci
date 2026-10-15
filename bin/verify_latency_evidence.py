# SPDX-License-Identifier: AGPL-3.0-only
"""Recompute an imported measurement; preserve its explicit measurement boundary."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def verify_evidence(report: dict[str, object], budget_ms: float = 5.) -> dict[str, object]:
    for key in ('measurement_scope','clock_domain','start_event','end_event','hardware'):
        if not isinstance(report.get(key),str) or not str(report[key]).strip():
            raise ValueError(f'Missing measurement metadata: {key}')
    modalities = report.get('modalities')
    if (not isinstance(modalities,list) or not modalities
            or any(x not in ('EEG','OPM-MEG','fNIRS') for x in modalities)):
        raise ValueError('Explicit measured modalities required')
    values = np.asarray(report.get('samples_ms',[]),dtype=float)
    if (values.ndim != 1 or len(values)<100 or not np.isfinite(values).all()
            or np.any(values<0) or not np.isfinite(budget_ms) or budget_ms<=0):
        raise ValueError('At least 100 finite nonnegative timing samples required')
    p99 = float(np.percentile(values,99))
    return {key:report[key] for key in ('measurement_scope','clock_domain','start_event',
                                       'end_event','hardware','modalities')} | {
        'samples':len(values),'p50_ms':float(np.percentile(values,50)),
        'p99_ms':p99,'maximum_ms':float(values.max()),'budget_ms':budget_ms,
        'passes_p99_budget':p99<budget_ms,
        'scope':'Timing arithmetic verified; authenticity and external instrumentation require review'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    result = verify_evidence(json.loads(raw))
    result['evidence_sha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result,indent=2))
    if not result['passes_p99_budget']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
