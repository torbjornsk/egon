"""
Helper script to update market sentiment manually
Use this when checking mrktedge.ai or your own analysis
"""

import json
from datetime import datetime
from pathlib import Path

def update_sentiment():
    """Interactive script to update sentiment"""
    config_path = Path('config/market_sentiment.json')
    
    print("\n" + "="*60)
    print("MARKET SENTIMENT UPDATE")
    print("="*60)
    print("\nBased on your analysis (mrktedge.ai, news, etc.)")
    print("Update the market sentiment for gold trading\n")
    
    # Get sentiment
    print("Sentiment options:")
    print("  1. Bullish (expecting gold to rise)")
    print("  2. Bearish (expecting gold to fall)")
    print("  3. Neutral (no clear direction)")
    
    choice = input("\nSelect sentiment (1-3): ").strip()
    
    sentiment_map = {
        '1': 'bullish',
        '2': 'bearish',
        '3': 'neutral'
    }
    
    sentiment = sentiment_map.get(choice, 'neutral')
    
    # Get confidence
    print(f"\nConfidence in {sentiment} sentiment:")
    print("  0.9-1.0 = Very high confidence")
    print("  0.7-0.9 = High confidence")
    print("  0.5-0.7 = Moderate confidence")
    print("  0.3-0.5 = Low confidence")
    
    confidence = input("\nEnter confidence (0.0-1.0): ").strip()
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except:
        confidence = 0.5
    
    # Get notes
    notes = input("\nOptional notes (press Enter to skip): ").strip()
    if not notes:
        notes = "Manual update"
    
    # Calculate score
    score_map = {
        'bullish': confidence,
        'bearish': -confidence,
        'neutral': 0.0
    }
    score = score_map[sentiment]
    
    # Create sentiment data
    sentiment_data = {
        'sentiment': sentiment,
        'confidence': confidence,
        'score': score,
        'last_updated': datetime.now().isoformat(),
        'source': 'manual',
        'notes': notes
    }
    
    # Save to file
    config_path.parent.mkdir(exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(sentiment_data, f, indent=2)
    
    print("\n" + "="*60)
    print("✓ Sentiment updated successfully!")
    print("="*60)
    print(f"Sentiment: {sentiment.upper()}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Score: {score:+.2f}")
    print(f"Notes: {notes}")
    print(f"\nSaved to: {config_path}")
    print("="*60 + "\n")
    
    # Show impact
    print("Impact on trading:")
    if sentiment == 'bullish' and confidence > 0.7:
        print("  → Will favor LONG positions")
        print("  → Position size increased by 30%")
    elif sentiment == 'bearish' and confidence > 0.7:
        print("  → Will favor SHORT positions")
        print("  → Position size increased by 30%")
    elif sentiment == 'neutral':
        print("  → Will take both LONG and SHORT signals")
        print("  → Normal position sizing")
    else:
        print("  → Low confidence - reduced position sizing")
    
    print()

if __name__ == '__main__':
    update_sentiment()
