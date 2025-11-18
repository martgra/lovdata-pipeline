"""Main module for running the Lovdata pipeline with Dagster."""

import sys

from dagster._core.definitions.definitions_class import Definitions


def main():
    """Run the Dagster pipeline."""
    from lovdata_pipeline import defs

    if not isinstance(defs, Definitions):
        print("Error: defs must be a Definitions object", file=sys.stderr)
        sys.exit(1)

    print("Lovdata Pipeline initialized successfully!")
    print("\nTo start the Dagster UI, run:")
    print("  dagster dev -m lovdata_pipeline")
    print("\nOr use the definitions directly:")
    print("  dagster-webserver -m lovdata_pipeline")


if __name__ == "__main__":
    main()
