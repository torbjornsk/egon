"""
Quick setup script for Alpha Vantage sentiment integration
"""

import json
from pathlib import Path

def setup_alpha_vantage():
    """Interactive setup for Alpha Vantage"""
    print("\n" + "="*60)
    print("ALPHA VANTAGE SETUP")
    print("="*60)
    
    print("\nStep 1: Get your free API key")
    print("Visit: https://www.alphavantage.co/support/#api-key")
    print("Fill out the form and copy your API key")
    
    api_key = input("\nPaste your API key here: ").strip()
    
    if not api_key or len(api_key) < 10:
        print("\n❌ Invalid API key. Please try again.")
        return
    
    # Update config
    config_path = Path('config/trend_params.json')
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['use_sentiment_filter'] = True
        config['sentiment_source'] = 'alpha_vantage'
        config['alpha_vantage_api_key'] = api_key
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\n✅ Configuration updated!")
        print(f"API key saved to: {config_path}")
        
        # Test the API
        print("\n" + "="*60)
        print("TESTING API CONNECTION")
        print("="*60)
        
        import sys
        sys.path.append(str(Path(__file__).parent))
        
        from src.integrations.alpha_vantage import AlphaVantageSentiment
        
        print("\nFetching sentiment from Alpha Vantage...")
        print("(This may take a few seconds)")
        
        sentiment = AlphaVantageSentiment(api_key)
        result = sentiment.get_gold_sentiment()
        
        print("\n✅ API connection successful!")
        print("\n" + "-"*60)
        print("CURRENT GOLD SENTIMENT")
        print("-"*60)
        print(f"Sentiment: {result['sentiment'].upper()}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Score: {result['score']:+.3f}")
        print(f"Source: {result['source']}")
        
        print("\n" + "="*60)
        print("✅ SETUP COMPLETE!")
        print("="*60)
        print("\nYou can now run the trend bot:")
        print("  python live_trading_bot_trend.py")
        print("\nThe bot will automatically fetch sentiment every hour.")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check your API key is correct")
        print("2. Verify internet connection")
        print("3. Try again in a few minutes (rate limit)")

if __name__ == '__main__':
    setup_alpha_vantage()
