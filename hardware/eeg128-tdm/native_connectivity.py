# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Compare native airwires by net so a smaller total cannot hide regressions."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


def airwire_counts(report: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for airwire in report['unconnected_items']:
        names = {match[1] for item in airwire['items']
                 if (match := re.search(r'\[([^]]+)\]', item['description']))}
        if len(names) != 1:
            raise ValueError('Ambiguous native airwire net')
        counts.update(names)
    return counts


def regressed_nets(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    old, new = airwire_counts(before), airwire_counts(after)
    return sorted(net for net, count in new.items() if count > old[net])
