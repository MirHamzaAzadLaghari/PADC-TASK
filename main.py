"""Premium Calculator - entry point.

    python main.py            # scientific layout (default)
    python main.py --basic    # compact standard layout
"""
import sys

from calculator.ui import run

if __name__ == "__main__":
    run(scientific="--basic" not in sys.argv)
