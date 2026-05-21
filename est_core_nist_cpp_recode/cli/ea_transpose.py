"""ea_transpose — Data Transpose CLI"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="ea_transpose — Transpose binary data")
    parser.add_argument("file", help="Binary data file")
    parser.add_argument("-o", "--output", required=True, help="Output file")
    args = parser.parse_args()

    r, c = 1000, 1000
    with open(args.file, 'rb') as f:
        data = f.read()

    if len(data) != r * c:
        print(f"Error: file must be {r * c} bytes, got {len(data)}", file=sys.stderr)
        sys.exit(1)

    transposed = bytearray(r * c)
    for j in range(c):
        for i in range(r):
            transposed[j * r + i] = data[i * c + j]

    with open(args.output, 'wb') as f:
        f.write(transposed)


if __name__ == "__main__":
    main()
