"""
Test historical sentiment queries with Alpha Vantage
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent.parent))

from src.integrations.alpha_vantage import AlphaVantageSentiment
import json

# Load API key
config_path = Path('config/trend_params.json')
with open(config_path, 'r') as f:
    config = json.load(f)

API_KEY = config.get('alpha_vantage_api_key', '')

if not API_KEY:
    print("No API key found")
    sys.exit(1)

print("\n" + "="*60)
print("TESTING HISTORICAL SENTIMENT QUERIES")
print("="*60)

sentiment_analyzer = AlphaVantageSentiment(API_KEY)

# Test 1: Current sentiment (no time range)
print("\nTest 1: Current sentiment (no time range)")
print("-" * 60)
try:
    current = sentiment_analyzer.get_gold_sentiment()
    print(f"✓ Sentiment: {current['sentiment']} (confidence: {current['confidence']:.2f})")
    print(f"  Score: {current['score']:+.3f}")
    print(f"  Source: {current['source']}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Historical sentiment (24 hours ago)
print("\nTest 2: Historical sentiment (24 hours ago)")
print("-" * 60)
try:
    time_to = datetime.now() - timedelta(hours=24)
    time_from = time_to - timedelta(hours=24)
    
    time_from_str = time_from.strftime('%Y%m%dT%H%M')
    time_to_str = time_to.strftime('%Y%m%dT%H%M')
    
    print(f"Querying: {time_from_str} to {time_to_str}")
    
    historical = sentiment_analyzer.get_gold_sentiment(time_from_str, time_to_str)
    print(f"✓ Sentiment: {historical['sentiment']} (confidence: {historical['confidence']:.2f})")
    print(f"  Score: {historical['score']:+.3f}")
    print(f"  Source: {historical['source']}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Historical sentiment (1 week ago)
print("\nTest 3: Historical sentiment (1 week ago)")
print("-" * 60)
try:
    time_to = datetime.now() - timedelta(days=7)
    time_from = time_to - timedelta(hours=24)
    
    time_from_str = time_from.strftime('%Y%m%dT%H%M')
    time_to_str = time_to.strftime('%Y%m%dT%H%M')
    
    print(f"Querying: {time_from_str} to {time_to_str}")
    
    historical = sentiment_analyzer.get_gold_sentiment(time_from_str, time_to_str)
    print(f"✓ Sentiment: {historical['sentiment']} (confidence: {historical['confidence']:.2f})")
    print(f"  Score: {historical['score']:+.3f}")
    print(f"  Source: {historical['source']}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("""
If all tests passed, Alpha Vantage supports historical queries!
This means we can backtest with real historical sentiment.

If tests failed with API errors, historical queries may not be
supported on the free tier, or the date format is incorrect.
""")
print("="*60 + "\n")
