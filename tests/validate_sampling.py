"""
Validate that stratified sampling produces statistically equivalent results
"""
import json
from test_suite_sampled import SampledTestSuite

def main():
    print("="*80)
    print("STATISTICAL SAMPLING VALIDATION")
    print("="*80)
    print("\nThis will test if 15% sampled data produces similar results to 100% data")
    print("Using stratified sampling based on market regimes (volatility + trend)\n")
    
    # Load current configs
    with open('config/m5_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Test M5 sampling
    print("\n" + "="*80)
    print("VALIDATING M5 SAMPLING")
    print("="*80)
    
    suite_m5 = SampledTestSuite(sample_ratio=0.15)
    m5_validation = suite_m5.validate_sampling(m5_config, timeframe='M5')
    
    # Test M1 sampling
    print("\n" + "="*80)
    print("VALIDATING M1 SAMPLING")
    print("="*80)
    
    suite_m1 = SampledTestSuite(sample_ratio=0.15)
    m1_validation = suite_m1.validate_sampling(m1_config, timeframe='M1')
    
    # Save validation results
    with open('tests/sampling_validation.json', 'w') as f:
        json.dump({
            'm5': m5_validation,
            'm1': m1_validation
        }, f, indent=2)
    
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\nIf sampling is valid (< 10% difference), you can use:")
    print("  - tests/optimize_m5_fast.py (uses sampling)")
    print("  - tests/optimize_m1_fast.py (uses sampling)")
    print("\nThese will be ~6-7x faster with minimal accuracy loss.")
    print("\nValidation results saved to: tests/sampling_validation.json")

if __name__ == '__main__':
    main()
