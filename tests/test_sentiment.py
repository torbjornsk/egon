"""
Test sentiment integration
Run this to verify Alpha Vantage or manual sentiment is working
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))

from src.integrations.alpha_vantage import AlphaVantageSentiment, ManualSentiment
import json

def test_manual_sentiment():
    """Test manual sentiment reading"""
    print("\n" + "="*60)
    print("TESTING MANUAL SENTIMENT")
    print("="*60)
    
    sentiment = ManualSentiment()
    result = sentiment.get_gold_sentiment()
    
    print(f"\nSentiment: {result['sentiment'].upper()}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Score: {result['score']:+.2f}")
    print(f"Source: {result['source']}")
    print(f"Last Updated: {result['last_updated']}")
    print(f"Notes: {result.get('notes', 'N/A')}")
    
    # Test trade filtering
    print("\n" + "-"*60)
    print("TRADE FILTERING TEST")
    print("-"*60)
    
    for signal in ['LONG', 'SHORT']:
        should_trade, confidence = sentiment.should_trade(signal)
        print(f"\n{signal} signal:")
        print(f"  Should trade: {should_trade}")
        print(f"  Confidence: {confidence:.2f}")
        
        if should_trade:
            base_size = 0.10
            adjusted = sentiment.adjust_position_size(base_size)
            print(f"  Position size: {base_size:.2f} → {adjusted:.2f} ({(adjusted/base_size-1)*100:+.0f}%)")
    
    print("\n" + "="*60)
    print("✓ Manual sentiment test complete")
    print("="*60 + "\n")

def test_alpha_vantage(api_key=None):
    """Test Alpha Vantage sentiment"""
    print("\n" + "="*60)
    print("TESTING ALPHA VANTAGE SENTIMENT")
    print("="*60)
    
    if not api_key:
        print("\n⚠️  No API key provided")
        print("Get free key: https://www.alphavantage.co/support/#api-key")
        print("\nUsage: python tests/test_sentiment.py YOUR_API_KEY")
        print("\nSkipping Alpha Vantage test...")
        return
    
    sentiment = AlphaVantageSentiment(api_key)
    
    print("\nFetching sentiment from Alpha Vantage...")
    print("(This may take a few seconds)")
    
    try:
        result = sentiment.get_gold_sentiment()
        
        print(f"\n✓ Sentiment fetched successfully!")
        print(f"\nSentiment: {result['sentiment'].upper()}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Score: {result['score']:+.2f}")
        print(f"Source: {result['source']}")
        print(f"Last Updated: {result['last_updated']}")
        
        # Test trade filtering
        print("\n" + "-"*60)
        print("TRADE FILTERING TEST")
        print("-"*60)
        
        for signal in ['LONG', 'SHORT']:
            should_trade, confidence = sentiment.should_trade(signal, result)
            print(f"\n{signal} signal:")
            print(f"  Should trade: {should_trade}")
            print(f"  Confidence: {confidence:.2f}")
            
            if should_trade:
                base_size = 0.10
                adjusted = sentiment.adjust_position_size(base_size, result)
                print(f"  Position size: {base_size:.2f} → {adjusted:.2f} ({(adjusted/base_size-1)*100:+.0f}%)")
        
        print("\n" + "="*60)
        print("✓ Alpha Vantage test complete")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nPossible issues:")
        print("  - Invalid API key")
        print("  - API rate limit exceeded")
        print("  - Network connection issue")
        print("\n" + "="*60 + "\n")

def show_config():
    """Show current trend bot config"""
    print("\n" + "="*60)
    print("CURRENT TREND BOT CONFIGURATION")
    print("="*60)
    
    config_path = Path(__file__).parent.parent / 'config' / 'trend_params.json'
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        print(f"\nSentiment Filter: {'ENABLED' if config.get('use_sentiment_filter') else 'DISABLED'}")
        
        if config.get('use_sentiment_filter'):
            source = config.get('sentiment_source', 'manual')
            print(f"Sentiment Source: {source.upper()}")
            
            if source == 'alpha_vantage':
                api_key = config.get('alpha_vantage_api_key', '')
                if api_key:
                    print(f"API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else ''}")
                else:
                    print("⚠️  API Key: NOT SET")
        
        print(f"\nPosition Size: {config.get('position_size_pct', 0.10)*100}%")
        print(f"Leverage: {config.get('leverage', 20)}x")
        print(f"Max Positions: {config.get('max_positions', 2)}")
        
    except Exception as e:
        print(f"\n✗ Error reading config: {e}")
    
    print("\n" + "="*60 + "\n")

if __name__ == '__main__':
    import sys
    
    # Show config
    show_config()
    
    # Test manual sentiment
    test_manual_sentiment()
    
    # Test Alpha Vantage if API key provided
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
        test_alpha_vantage(api_key)
    else:
        print("\n" + "="*60)
        print("ALPHA VANTAGE TEST SKIPPED")
        print("="*60)
        print("\nTo test Alpha Vantage:")
        print("  python tests/test_sentiment.py YOUR_API_KEY")
        print("\nGet free API key:")
        print("  https://www.alphavantage.co/support/#api-key")
        print("\n" + "="*60 + "\n")
