"""
Test MRKTedge scraper
Run this to verify the scraper can login and fetch sentiment
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).parent.parent))

from src.integrations.mrktedge_scraper import MRKTedgeScraper
import logging

logging.basicConfig(level=logging.INFO)

def test_mrktedge():
    """Test mrktedge scraper"""
    print("\n" + "="*60)
    print("TESTING MRKTEDGE SCRAPER")
    print("="*60)
    
    scraper = MRKTedgeScraper()
    
    if not scraper.credentials:
        print("\n⚠️  No credentials found!")
        print("\nPlease update: config/mrktedge_credentials.json")
        print("\nExample:")
        print('{')
        print('  "email": "your_email@example.com",')
        print('  "password": "your_password"')
        print('}')
        print("\n" + "="*60 + "\n")
        return
    
    print(f"\nCredentials loaded: {scraper.credentials['email']}")
    print("\nAttempting login...")
    
    if scraper.login():
        print("✓ Login successful!")
        
        print("\nFetching gold sentiment...")
        sentiment = scraper.get_gold_sentiment()
        
        print("\n" + "-"*60)
        print("SENTIMENT DATA")
        print("-"*60)
        print(f"Sentiment: {sentiment['sentiment'].upper()}")
        print(f"Confidence: {sentiment['confidence']:.2f}")
        print(f"Score: {sentiment['score']:+.2f}")
        print(f"Source: {sentiment['source']}")
        print(f"Last Updated: {sentiment['last_updated']}")
        
        if 'details' in sentiment:
            print(f"\nDetails:")
            for key, value in sentiment['details'].items():
                print(f"  {key}: {value}")
        
        # Test trade filtering
        print("\n" + "-"*60)
        print("TRADE FILTERING TEST")
        print("-"*60)
        
        for signal in ['LONG', 'SHORT']:
            should_trade, confidence = scraper.should_trade(signal, sentiment)
            print(f"\n{signal} signal:")
            print(f"  Should trade: {should_trade}")
            print(f"  Confidence: {confidence:.2f}")
            
            if should_trade:
                base_size = 0.10
                adjusted = scraper.adjust_position_size(base_size, sentiment)
                print(f"  Position size: {base_size:.2f} → {adjusted:.2f} ({(adjusted/base_size-1)*100:+.0f}%)")
        
        print("\n" + "="*60)
        print("✓ MRKTedge scraper test complete")
        print("="*60 + "\n")
        
    else:
        print("✗ Login failed!")
        print("\nTroubleshooting:")
        print("1. Check credentials in config/mrktedge_credentials.json")
        print("2. Verify your mrktedge.ai subscription is active")
        print("3. Try logging in manually at https://www.mrktedge.ai/login")
        print("4. The site structure may have changed - scraper needs updating")
        print("\n" + "="*60 + "\n")

if __name__ == '__main__':
    test_mrktedge()
