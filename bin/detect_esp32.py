# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import argparse, os, sys

def find() -> str:
    if os.path.exists("/dev/bci-esp32"):
        return "/dev/bci-esp32"
    try:
        from serial.tools import list_ports
        for port in list_ports.comports():
            desc = " ".join(str(x or "") for x in (port.description, port.manufacturer, port.product)).lower()
            if port.vid == 0x303A or "espressif" in desc or "esp32" in desc:
                return port.device
    except Exception:
        return ""
    return ""

def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--present", action="store_true")
    g.add_argument("--absent", action="store_true")
    g.add_argument("--print", action="store_true", dest="print_path")
    a = p.parse_args()
    path = find()
    if a.print_path:
        print(path); return
    if a.present: sys.exit(0 if path else 1)
    if a.absent: sys.exit(0 if not path else 1)

if __name__ == "__main__":
    main()
