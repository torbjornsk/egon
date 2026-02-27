# MRKTedge.ai Scraper Setup Guide

## Overview

The trend bot can now automatically scrape sentiment data from mrktedge.ai. No manual updates needed!

## Setup Steps

### 1. Add Your Credentials

Edit `config/mrktedge_credentials.json`:

```json
{
  "email": "your_actual_email@example.com",
  "password": "your_actual_password"
}
```

**Important**: This file is in `.gitignore` - your credentials stay private and won't be committed to git.

### 2. Configure the Trend Bot

Edit `config/trend_params.json`:

```json
{
  "use_sentiment_filter": true,
  "sentiment_source": "mrktedge"
}
```

### 3. Test the Scraper

```bash
python tests/test_mrktedge_scraper.py
```

This will:
- Load your credentials
- Login to mrktedge.ai
- Fetch gold sentiment
- Show you the extracted data

### 4. Run the Trend Bot

```bash
python live_trading_bot_trend.py
```

The bot will automatically:
- Login to mrktedge every hour
- Scrape gold sentiment
- Cache results for 60 minutes
- Filter trades based on sentiment

## How It Works

### Login Process
1. Scraper loads credentials from `config/mrktedge_credentials.json`
2. Sends login request to mrktedge.ai
3. Maintains session cookies for subsequent requests

### Sentiment Extraction
1. Fetches the dashboard page
2. Searches for gold/XAUUSD sentiment indicators
3. Analyzes keywords (bullish, bearish, neutral)
4. Extracts confidence scores
5. Caches results for 1 hour

### Trade Filtering
- **LONG signal + Bullish sentiment** → Take trade
- **SHORT signal + Bearish sentiment** → Take trade
- **Neutral sentiment** → Take trade with normal size
- **Conflicting signals** → Skip trade

### Position Sizing
- **High confidence (>80%)** → 30% larger position
- **Medium confidence (60-80%)** → 10% larger position
- **Low confidence (<40%)** → 30% smaller position
- **Normal confidence** → Standard position size

## Troubleshooting

### Login Fails

**Check credentials:**
```bash
cat config/mrktedge_credentials.json
```

Make sure email and password are correct.

**Test manually:**
1. Go to https://www.mrktedge.ai/login
2. Try logging in with your credentials
3. If it works there but not in scraper, the site structure may have changed

### No Sentiment Extracted

The scraper uses keyword analysis to extract sentiment. If mrktedge changes their layout, you may need to update the scraper.

**Check what was scraped:**
```bash
cat data/mrktedge_cache.json
```

**Update scraper:**
Edit `src/integrations/mrktedge_scraper.py` and adjust the `_extract_sentiment_from_page()` method.

### Site Structure Changed

If mrktedge.ai updates their website, the scraper may need adjustments:

1. Open `src/integrations/mrktedge_scraper.py`
2. Update the `_scrape_sentiment()` method
3. Adjust CSS selectors or keyword patterns
4. Test with `python tests/test_mrktedge_scraper.py`

## Customization

### Change Cache Duration

Edit `src/integrations/mrktedge_scraper.py`:

```python
self.cache_duration_minutes = 60  # Change to 30, 120, etc.
```

### Adjust Sentiment Keywords

Edit the `sentiment_keywords` dict in `_extract_sentiment_from_page()`:

```python
sentiment_keywords = {
    'bullish': ['bullish', 'buy', 'long', 'positive', 'uptrend', 'rally'],
    'bearish': ['bearish', 'sell', 'short', 'negative', 'downtrend', 'drop'],
    'neutral': ['neutral', 'sideways', 'ranging', 'mixed', 'consolidation']
}
```

### Change Position Size Multipliers

Edit `adjust_position_size()` in `src/integrations/mrktedge_scraper.py`:

```python
if confidence > 0.8:
    multiplier = 1.5  # Was 1.3 (30% larger, now 50%)
elif confidence > 0.6:
    multiplier = 1.2  # Was 1.1 (10% larger, now 20%)
```

## Alternative: Alpha Vantage

If the scraper doesn't work or you prefer an API:

1. Get free API key: https://www.alphavantage.co/support/#api-key

2. Update `config/trend_params.json`:
```json
{
  "use_sentiment_filter": true,
  "sentiment_source": "alpha_vantage",
  "alpha_vantage_api_key": "YOUR_KEY_HERE"
}
```

3. Test:
```bash
python tests/test_sentiment.py YOUR_API_KEY
```

## Security Notes

### Credentials Safety
- `config/mrktedge_credentials.json` is in `.gitignore`
- Never commit this file to git
- Never share your credentials
- Use a strong, unique password

### Session Management
- Scraper maintains login session
- Session expires after inactivity
- Scraper automatically re-logs in if needed

### Rate Limiting
- Scraper caches results for 1 hour
- Reduces load on mrktedge servers
- Avoids potential rate limiting

## Comparison: MRKTedge vs Alpha Vantage

| Feature | MRKTedge Scraper | Alpha Vantage API |
|---------|------------------|-------------------|
| Cost | Subscription ($42/mo) | Free tier available |
| Gold-specific | ✓ Yes | ✗ Generic news |
| Real-time | ✓ Yes | ✓ Yes |
| Reliability | Depends on site | ✓ Stable API |
| Setup | Credentials | API key |
| Maintenance | May need updates | Stable |
| Accuracy | High (gold-focused) | Medium (general) |

## Recommendation

**Use MRKTedge scraper if:**
- You already have mrktedge subscription
- You want gold-specific sentiment
- You're okay with occasional scraper updates

**Use Alpha Vantage if:**
- You want set-and-forget automation
- You prefer API stability
- You don't have mrktedge subscription

**Use Manual if:**
- You want full control
- You check mrktedge daily anyway
- You prefer to set sentiment yourself

## Support

If you encounter issues:

1. **Test the scraper**: `python tests/test_mrktedge_scraper.py`
2. **Check logs**: `trading_bot_trend.log`
3. **Verify credentials**: `config/mrktedge_credentials.json`
4. **Check cache**: `data/mrktedge_cache.json`
5. **Try manual login**: https://www.mrktedge.ai/login

## Next Steps

1. ✅ Add credentials to `config/mrktedge_credentials.json`
2. ✅ Test scraper: `python tests/test_mrktedge_scraper.py`
3. ✅ Configure trend bot: `config/trend_params.json`
4. ✅ Run trend bot: `python live_trading_bot_trend.py`
5. ⏳ Monitor performance and adjust as needed

---

**Note**: Web scraping may violate mrktedge.ai's Terms of Service. Check their ToS before using. Consider contacting them about API access as an alternative.
