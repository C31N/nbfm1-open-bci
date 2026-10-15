#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Evaluate a dated complete EUR component quote; never guess missing prices."""
from __future__ import annotations
import argparse
import csv
from datetime import date
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path


def evaluate(bom: list[dict[str,str]], quote: dict[str,object], today: date) -> dict[str,object]:
    if not bom:
        raise ValueError('A complete nonempty BOM is required')
    age = (today-date.fromisoformat(str(quote['date']))).days
    if quote.get('currency') != 'EUR' or not 0 <= age <= 7:
        raise ValueError('A EUR quote no older than seven days is required')
    lines = quote.get('parts')
    if not isinstance(lines,dict):
        raise ValueError('Quote requires parts indexed by LCSC code')
    totals = []
    for row in bom:
        code,qty = row['LCSC Part #'],int(row['Qty'])
        part = lines[code]
        price = Decimal(str(part['unit_price_eur']))
        multiple, minimum = int(part['multiple']),int(part['minimum'])
        if (not price.is_finite() or price<=0 or multiple<1 or minimum<1
                or qty<1 or part.get('mpn') != row['Manufacturer Part #']):
            raise ValueError(f'Invalid quote identity or pricing: {code}')
        purchased = int((Decimal(max(qty,minimum))/multiple).to_integral_value(rounding=ROUND_CEILING))*multiple
        if int(part['price_tier_minimum'])>purchased or int(part['stock'])<purchased:
            raise ValueError(f'Unavailable quantity or invalid price tier: {code}')
        totals.append((code,price*qty,price*purchased))
    component = sum((x[1] for x in totals),Decimal(0))
    purchase = sum((x[2] for x in totals),Decimal(0))
    return {'quote_date':quote['date'],'currency':'EUR','complete_bom_lines':len(totals),
            'component_cost_eur':str(component),'purchase_cost_eur':str(purchase),
            'component_target_under_50_eur':component<50,'purchase_under_50_eur':purchase<50,
            'excludes':'PCB, assembly, feeder charges, shipping, tax, isolation and sensors'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('quote',type=Path)
    args = parser.parse_args()
    with (Path(__file__).parent/'BOM.csv').open(newline='') as stream:
        bom = list(csv.DictReader(stream))
    result = evaluate(bom,json.loads(args.quote.read_text()),date.today())
    print(json.dumps(result,indent=2))
    if not result['component_target_under_50_eur']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
