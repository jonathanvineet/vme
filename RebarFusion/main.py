import argparse
import os

from extract_rebars import RebarExtractor


def print_banner():

    print("=" * 60)
    print("              REBAR EXTRACTOR")
    print("=" * 60)


def validate_input(path):

    if not os.path.exists(path):
        raise FileNotFoundError(path)

    extension = os.path.splitext(path)[1].lower()

    if extension not in [".dwg", ".dxf", ".pdf"]:
        raise Exception(
            "Supported files are DWG, DXF and vector PDF."
        )

    return extension


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "drawing",
        help="Path to DWG/DXF/PDF"
    )

    parser.add_argument(
        "--output",
        default="output",
        help="Output folder"
    )

    args = parser.parse_args()

    print_banner()

    validate_input(args.drawing)

    print("\nReading drawing...")

    extractor = RebarExtractor(args.drawing, args.output)
    result = extractor.run()

    print(f"Instances Loaded : {len(result.instances)}")
    print(f"Families Found   : {len(result.families)}")

    print("\nFinished!")
    print("Results written to:", args.output)


if __name__ == "__main__":
    main()