"""ea_non_iid — Non-IID Entropy Assessment CLI"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ea.non_iid_pipeline import run_non_iid_test


def main():
    parser = argparse.ArgumentParser(description="ea_non_iid — Non-IID Entropy Assessment")
    parser.add_argument("file", help="Binary data file")
    parser.add_argument("bits_per_symbol", nargs="?", type=int, default=0,
                        help="Bits per symbol (0 = auto-detect)")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args()

    run = run_non_iid_test(
        file_path=args.file,
        bits_per_symbol=args.bits_per_symbol,
        verbose=args.verbose,
    )

    print(json.dumps(run.to_dict(), indent=2))


if __name__ == "__main__":
    main()
