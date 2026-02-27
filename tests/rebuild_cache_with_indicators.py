"""
Rebuild cache with pre-computed indicators
Run this once to speed up all future tests
"""
from test_suite import TestSuite

def main():
    print("="*80)
    print("REBUILDING CACHE WITH PRE-COMPUTED INDICATORS")
    print("="*80)
    print("\nThis will:")
    print("  1. Fetch data from MT5 (if not cached)")
    print("  2. Pre-compute all indicator variations")
    print("  3. Save to cache for instant access")
    print("\nThis takes a few minutes but only needs to be done once.")
    print("Future tests will be 10-20x faster!\n")
    
    suite = TestSuite()
    suite.fetch_and_cache_data(force_refresh=True)
    
    print("\n" + "="*80)
    print("CACHE REBUILT SUCCESSFULLY")
    print("="*80)
    print("\nYou can now run optimizations much faster:")
    print("  - python tests/optimize_m5.py")
    print("  - python tests/optimize_m1.py")
    print("\nOr use Monte Carlo sampling:")
    print("  - python tests/optimize_m5_monte_carlo.py")
    print("  - python tests/optimize_m1_monte_carlo.py")

if __name__ == '__main__':
    main()
