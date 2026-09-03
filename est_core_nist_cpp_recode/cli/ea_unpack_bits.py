"""ea_unpack_bits — Bit Unpack CLI

Expands a packed bitstream (8 bits per byte) into the one-sample-per-byte form
NIST SP 800-90B expects, so a file collected as raw bits can be read by the EA
CLIs without a word size. Output bytes are 0x00 / 0x01, MSB first.
"""

import argparse
import os
import sys

CHUNK_SIZE = 1024 * 1024  # 1MB chunks for memory efficiency


def unpack_file(input_path: str, output_path: str) -> None:
    """Unpacks a bitstream file."""
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    input_size = os.path.getsize(input_path)
    print(f"Input file: {input_path} ({input_size:,} bytes)")
    print(f"Output file: {output_path}")
    print("Unpacking bits (MSB first)...")

    total_bits = 0
    with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
        while True:
            chunk = fin.read(CHUNK_SIZE)
            if not chunk:
                break

            unpacked = bytearray(len(chunk) * 8)
            idx = 0
            for byte in chunk:
                for i in range(7, -1, -1):
                    unpacked[idx] = (byte >> i) & 1
                    idx += 1

            fout.write(unpacked)
            total_bits += len(unpacked)

    output_size = os.path.getsize(output_path)
    print(f"Done. Wrote {total_bits:,} bits ({output_size:,} bytes).")


def main():
    parser = argparse.ArgumentParser(
        description="ea_unpack_bits — Unpack packed bitstream to NIST EA format")
    parser.add_argument("input", help="Input packed binary file")
    parser.add_argument("-o", "--output", help="Output unpacked file (default: <input>_unpacked.bin)")
    args = parser.parse_args()

    output_path = args.output
    if not output_path:
        base, ext = os.path.splitext(args.input)
        output_path = f"{base}_unpacked{ext}"

    unpack_file(args.input, output_path)


if __name__ == "__main__":
    main()
