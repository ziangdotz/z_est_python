"""ea_iid — IID Entropy Assessment CLI"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ea.iid_pipeline import run_iid_test


def main():
    parser = argparse.ArgumentParser(description="ea_iid — IID Entropy Assessment")
    parser.add_argument("file", help="Binary data file")
    parser.add_argument("bits_per_symbol", nargs="?", type=int, default=0,
                        help="Bits per symbol (0 = auto-detect)")
    parser.add_argument("-i", "--initial", action="store_true", dest="initial",
                        help="Initial entropy estimate (default)")
    parser.add_argument("-c", "--conditioned", action="store_false", dest="initial",
                        help="Conditioned dataset estimate")
    parser.add_argument("-a", "--all", action="store_true", dest="all_bits",
                        help="Use all bits for H_bitstring (default)")
    parser.add_argument("-t", "--truncate", action="store_false", dest="all_bits",
                        help="Truncate H_bitstring to first million bits")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args()

    parser.set_defaults(initial=True, all_bits=True)

    run = run_iid_test(
        file_path=args.file,
        bits_per_symbol=args.bits_per_symbol,
        initial=args.initial,
        all_bits=args.all_bits,
        verbose=args.verbose,
    )

    print(json.dumps(run.to_dict(), indent=2))


if __name__ == "__main__":
    main()
