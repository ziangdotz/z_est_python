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
    parser.add_argument("-a", "--all", action="store_true", dest="all_bits",
                        help="Use all bits for H_bitstring (default)")
    parser.add_argument("-t", "--truncate", action="store_false", dest="all_bits",
                        help="Truncate H_bitstring to first million bits")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    parser.add_argument("-j", "--workers", type=int, default=None, metavar="N",
                        help="processes the estimates may spread over "
                             "(default: one per physical core, 1 = no multiprocessing)")
    parser.set_defaults(all_bits=True)
    args = parser.parse_args()

    run = run_non_iid_test(
        file_path=args.file,
        bits_per_symbol=args.bits_per_symbol,
        verbose=args.verbose,
        all_bits=args.all_bits,
        num_workers=args.workers,
    )

    print(json.dumps(run.to_dict(), indent=2))


if __name__ == "__main__":
    main()
