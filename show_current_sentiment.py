"""Show current sentiment from Alpha Vantage"""
import sys
sys.path.append('.')
from src.integrations.alpha_vantage import AlphaVantageSentiment

sentiment = AlphaVantageSentiment('BUIA164I9ML3E2MW')
result = sentiment.get_gold_sentiment()

print('\nCurrent Gold Sentiment Analysis:')
print('='*60)
print(f'Sentiment: {result["sentiment"].upper()}')
print(f'Confidence: {result["confidence"]:.2f}')
print(f'Score: {result["score"]:+.3f}')
print(f'Source: Alpha Vantage (50 news articles)')
print(f'Updated: {result["last_updated"]}')
print('='*60)
print('\nThis sentiment is based on:')
print('- 50 most recent financial news articles')
print('- Weighted by relevance and recency')
print('- Adjusted for gold correlation (inverse USD)')
print('- Cached for 1 hour')
print()
