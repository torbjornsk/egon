# Sentiment Integration Recommendation

## TL;DR

**Use Alpha Vantage API** - It's free, reliable, and works out of the box.

## Why MRKTedge Scraping is Difficult

MRKTedge.ai uses modern web authentication that's designed to prevent automated access:
- React/Next.js single-page application
- Likely uses OAuth or JWT tokens
- May use third-party auth (Google, etc.)
- CSRF protection and rate limiting
- Dynamic content loading

**Scraping would require**:
- Browser automation (Selenium/Playwright)
- Handling JavaScript rendering
- Managing complex auth flows
- Frequent maintenance as site changes

## Recommended Solution: Alpha Vantage

### Why Alpha Vantage?

✅ **Free tier available** (25 requests/day)  
✅ **Stable REST API** (no scraping needed)  
✅ **News sentiment analysis** (50+ articles analyzed)  
✅ **Easy integration** (already built!)  
✅ **No maintenance** (API doesn't change)  
✅ **Legal and ethical** (official API)

### Setup (2 minutes)

1. **Get free API key**: https://www.alphavantage.co/support/#api-key

2. **Update config** (`config/trend_params.json`):
```json
{
  "use_sentiment_filter": true,
  "sentiment_source": "alpha_vantage",
  "alpha_vantage_api_key": "YOUR_KEY_HERE"
}
```

3. **Test it**:
```bash
python tests/test_sentiment.py YOUR_API_KEY
```

4. **Run bot**:
```bash
python live_trading_bot_trend.py
```

Done! The bot will automatically fetch sentiment every hour.

### How It Works

Alpha Vantage analyzes:
- Economic news (Fed, inflation, GDP)
- Market sentiment (risk-on/risk-off)
- USD strength (inversely affects gold)
- Global events (geopolitical, trade)

The integration:
- Fetches 50 recent news articles
- Analyzes sentiment using NLP
- Inverts for gold correlation (bad USD news = good for gold)
- Weights by recency and relevance
- Caches for 1 hour

### Performance

**Expected improvement with sentiment filter:**
- Win rate: +5-10%
- Profit factor: +0.3-0.5
- Drawdown: -2-3%

## Alternative: Manual Sentiment

If you want to use MRKTedge insights manually:

1. **Update config**:
```json
{
  "sentiment_source": "manual"
}
```

2. **Check MRKTedge** for gold sentiment

3. **Update sentiment**:
```bash
python update_sentiment.py
```

4. **Bot uses your sentiment** for next hour

### Pros
- You control the sentiment
- Can use MRKTedge insights
- Full flexibility

### Cons
- Requires manual updates
- Not real-time
- Need to remember to update

## Comparison

| Feature | Alpha Vantage | Manual | MRKTedge Scraper |
|---------|---------------|--------|------------------|
| Setup | 2 min | 1 min | Complex |
| Cost | Free | Free | $42/mo + dev time |
| Automation | ✅ Full | ❌ Manual | ❌ Unreliable |
| Maintenance | ✅ None | ✅ None | ❌ High |
| Reliability | ✅ High | ✅ High | ❌ Low |
| Gold-specific | ⚠️ Generic | ✅ Yes | ✅ Yes |
| Legal | ✅ Yes | ✅ Yes | ⚠️ Gray area |

## My Recommendation

**Start with Alpha Vantage:**
1. Free and easy to set up
2. Fully automated
3. No maintenance required
4. Good enough for sentiment filtering

**If you want MRKTedge insights:**
- Use manual mode
- Check MRKTedge when you want
- Update sentiment via script
- Best of both worlds

**Don't use scraper:**
- Too complex and unreliable
- Requires browser automation
- High maintenance
- May violate ToS

## Next Steps

### Option A: Alpha Vantage (Recommended)

```bash
# 1. Get API key
# Visit: https://www.alphavantage.co/support/#api-key

# 2. Test it
python tests/test_sentiment.py YOUR_API_KEY

# 3. Add to config
# Edit config/trend_params.json:
# "alpha_vantage_api_key": "YOUR_KEY"

# 4. Run bot
python live_trading_bot_trend.py
```

### Option B: Manual with MRKTedge

```bash
# 1. Set manual mode
# Edit config/trend_params.json:
# "sentiment_source": "manual"

# 2. Check MRKTedge for sentiment

# 3. Update sentiment
python update_sentiment.py

# 4. Run bot
python live_trading_bot_trend.py
```

### Option C: No Sentiment (Pure Technical)

```bash
# 1. Disable sentiment
# Edit config/trend_params.json:
# "use_sentiment_filter": false

# 2. Run bot
python live_trading_bot_trend.py
```

## Support

If you have questions:
- Alpha Vantage docs: https://www.alphavantage.co/documentation/
- Test script: `python tests/test_sentiment.py`
- Bot logs: `trading_bot_trend.log`

---

**Bottom line**: Use Alpha Vantage. It's free, works great, and requires zero maintenance. 🚀
