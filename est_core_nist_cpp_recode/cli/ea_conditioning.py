"""ea_conditioning — Conditioning Evaluation CLI"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ea.conditioning import conditioning_test


def main():
    parser = argparse.ArgumentParser(description="ea_conditioning — Conditioning Assessment")
    parser.add_argument("h_in", type=float, help="Input entropy")
    parser.add_argument("n_in", type=int, help="Input bit width")
    parser.add_argument("n_out", type=int, help="Output bit width")
    parser.add_argument("nw", type=int, help="Internal state width")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args()

    result = conditioning_test(
        h_in=args.h_in,
        n_in=args.n_in,
        n_out=args.n_out,
        nw=args.nw,
        verbose=args.verbose,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
