"""ea_restart — Restart Test CLI"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ea.restart import restart_test


def main():
    parser = argparse.ArgumentParser(description="ea_restart — Restart Entropy Assessment")
    parser.add_argument("file", help="Binary data file")
    parser.add_argument("H_I", type=float, help="Initial entropy estimate")
    parser.add_argument("--iid", action="store_true", help="Run IID validation")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args()

    try:
        h_min = restart_test(
            file_path=args.file,
            H_I=args.H_I,
            iid=args.iid,
            verbose=args.verbose,
        )
        result = {"h_min": h_min, "H_I": args.H_I}
        print(json.dumps(result, indent=2))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
