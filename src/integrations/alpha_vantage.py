"""
Alpha Vantage News Sentiment Integration
Provides real-time market sentiment for gold trading
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

class AlphaVantageSentiment:
    def __init__(self, api_key=None):
        """Initialize Alpha Vantage sentiment analyzer
        
        Args:
            api_key: Alpha Vantage API key (get free at https://www.alphavantage.co/support/#api-key)
        """
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        self.cache_file = Path("data/sentiment_cache.json")
        self.cache_duration_minutes = 60  # Cache sentiment for 1 hour
        self.logger = logging.getLogger(__name__)
        
        # Ensure data directory exists
        self.cache_file.parent.mkdir(exist_ok=True)
        
    def get_gold_sentiment(self):
        """Get current market sentiment for gold
        
        Returns:
            dict: {
                'sentiment': 'bullish'|'bearish'|'neutral',
                'confidence': 0.0-1.0,
                'score': -1.0 to 1.0,
                'last_updated': timestamp,
                'source': 'alpha_vantage'|'cache'|'manual'
            }
        """
        # Check cache first
        cached = self._load_cache()
        if cached and self._is_cache_valid(cached):
            self.logger.info(f"Using cached sentiment: {cached['sentiment']} ({cached['confidence']:.2f})")
            return cached
        
        # If no API key, return neutral
        if not self.api_key:
            self.logger.warning("No Alpha Vantage API key - using neutral sentiment")
            return self._neutral_sentiment()
        
        # Fetch fresh sentiment
        try:
            sentiment = self._fetch_sentiment()
            self._save_cache(sentiment)
            return sentiment
        except Exception as e:
            self.logger.error(f"Error fetching sentiment: {e}")
            # Return cached even if expired, or neutral
            return cached if cached else self._neutral_sentiment()
    
    def _fetch_sentiment(self):
        """Fetch sentiment from Alpha Vantage API"""
        # Get news sentiment for gold-related topics
        params = {
            'function': 'NEWS_SENTIMENT',
            'topics': 'finance',
            'apikey': self.api_key,
            'limit': 50  # Get recent 50 articles
        }
        
        response = requests.get(self.base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Check for API errors
        if 'Error Message' in data:
            raise ValueError(f"API Error: {data['Error Message']}")
        if 'Information' in data:
            raise ValueError(f"API Info: {data['Information']}")
        if 'Note' in data:
            raise ValueError(f"API Note (rate limit?): {data['Note']}")
        
        if 'feed' not in data:
            raise ValueError(f"Unexpected API response: {data}")
        
        # Analyze sentiment from news feed
        sentiment_score = self._analyze_news_feed(data['feed'])
        
        # Convert score to sentiment label
        if sentiment_score > 0.15:
            sentiment = 'bullish'
            confidence = min(abs(sentiment_score), 1.0)
        elif sentiment_score < -0.15:
            sentiment = 'bearish'
            confidence = min(abs(sentiment_score), 1.0)
        else:
            sentiment = 'neutral'
            confidence = 1.0 - abs(sentiment_score)
        
        result = {
            'sentiment': sentiment,
            'confidence': confidence,
            'score': sentiment_score,
            'last_updated': datetime.now().isoformat(),
            'source': 'alpha_vantage'
        }
        
        self.logger.info(f"Fetched sentiment: {sentiment} (score: {sentiment_score:.3f}, confidence: {confidence:.2f})")
        return result
    
    def _analyze_news_feed(self, feed):
        """Analyze news feed and calculate aggregate sentiment
        
        Gold is inversely correlated with USD strength and risk-on sentiment
        """
        if not feed:
            return 0.0
        
        total_score = 0.0
        total_relevance = 0.0
        
        for article in feed:
            # Get overall sentiment score
            overall_score = float(article.get('overall_sentiment_score', 0))
            
            # Weight by relevance and recency
            relevance = float(article.get('relevance_score', 0.5))
            
            # Time decay: newer articles matter more
            time_published = article.get('time_published', '')
            age_hours = self._get_article_age_hours(time_published)
            time_weight = max(0.1, 1.0 - (age_hours / 48))  # Decay over 48 hours
            
            weight = relevance * time_weight
            
            # Invert sentiment for gold (bad news for USD = good for gold)
            # But also consider risk-off sentiment (good for gold)
            gold_adjusted_score = -overall_score * 0.7  # Inverse USD correlation
            
            total_score += gold_adjusted_score * weight
            total_relevance += weight
        
        # Calculate weighted average
        if total_relevance > 0:
            avg_score = total_score / total_relevance
        else:
            avg_score = 0.0
        
        # Normalize to -1 to 1 range
        return max(-1.0, min(1.0, avg_score))
    
    def _get_article_age_hours(self, time_published):
        """Calculate article age in hours"""
        try:
            # Alpha Vantage format: YYYYMMDDTHHMMSS
            pub_time = datetime.strptime(time_published, '%Y%m%dT%H%M%S')
            age = datetime.now() - pub_time
            return age.total_seconds() / 3600
        except:
            return 24  # Default to 24 hours if parsing fails
    
    def _neutral_sentiment(self):
        """Return neutral sentiment"""
        return {
            'sentiment': 'neutral',
            'confidence': 0.5,
            'score': 0.0,
            'last_updated': datetime.now().isoformat(),
            'source': 'default'
        }
    
    def _load_cache(self):
        """Load sentiment from cache file"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Error loading cache: {e}")
        return None
    
    def _save_cache(self, sentiment):
        """Save sentiment to cache file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(sentiment, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Error saving cache: {e}")
    
    def _is_cache_valid(self, cached):
        """Check if cached sentiment is still valid"""
        try:
            last_updated = datetime.fromisoformat(cached['last_updated'])
            age = datetime.now() - last_updated
            return age.total_seconds() < (self.cache_duration_minutes * 60)
        except:
            return False
    
    def should_trade(self, technical_signal, sentiment=None):
        """Decide if technical signal should be taken based on sentiment
        
        Args:
            technical_signal: 'LONG' or 'SHORT'
            sentiment: Optional sentiment dict (fetches if not provided)
            
        Returns:
            tuple: (should_trade: bool, confidence: float)
        """
        if sentiment is None:
            sentiment = self.get_gold_sentiment()
        
        signal_sentiment = sentiment['sentiment']
        confidence = sentiment['confidence']
        
        # Sentiment filter: only trade when sentiment aligns
        if technical_signal == 'LONG' and signal_sentiment == 'bullish':
            return True, confidence
        elif technical_signal == 'SHORT' and signal_sentiment == 'bearish':
            return True, confidence
        elif signal_sentiment == 'neutral':
            # Neutral sentiment: allow trade but with lower confidence
            return True, 0.5
        else:
            # Conflicting signals: skip trade
            self.logger.info(f"Skipping {technical_signal} - sentiment is {signal_sentiment}")
            return False, 0.0
    
    def adjust_position_size(self, base_size, sentiment=None):
        """Adjust position size based on sentiment confidence
        
        Args:
            base_size: Base position size (e.g., 0.10 for 10%)
            sentiment: Optional sentiment dict
            
        Returns:
            float: Adjusted position size
        """
        if sentiment is None:
            sentiment = self.get_gold_sentiment()
        
        confidence = sentiment['confidence']
        
        # Adjust size based on confidence
        if confidence > 0.8:
            multiplier = 1.3  # 30% larger
        elif confidence > 0.6:
            multiplier = 1.1  # 10% larger
        elif confidence < 0.4:
            multiplier = 0.7  # 30% smaller
        else:
            multiplier = 1.0  # Normal size
        
        adjusted = base_size * multiplier
        self.logger.debug(f"Position size: {base_size:.3f} -> {adjusted:.3f} (confidence: {confidence:.2f})")
        return adjusted


# Manual sentiment override
class ManualSentiment:
    """Simple manual sentiment for when you want to set it yourself"""
    
    def __init__(self, config_path='config/market_sentiment.json'):
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)
        
        # Create default config if doesn't exist
        if not self.config_path.exists():
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default sentiment config"""
        default = {
            'sentiment': 'neutral',
            'confidence': 0.5,
            'score': 0.0,
            'last_updated': datetime.now().isoformat(),
            'source': 'manual',
            'notes': 'Update this file based on mrktedge.ai or your analysis'
        }
        
        self.config_path.parent.mkdir(exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default, f, indent=2)
        
        self.logger.info(f"Created default sentiment config: {self.config_path}")
    
    def get_gold_sentiment(self):
        """Read sentiment from config file"""
        try:
            with open(self.config_path, 'r') as f:
                sentiment = json.load(f)
            
            self.logger.info(f"Manual sentiment: {sentiment['sentiment']} ({sentiment['confidence']:.2f})")
            return sentiment
        except Exception as e:
            self.logger.error(f"Error reading sentiment config: {e}")
            return {
                'sentiment': 'neutral',
                'confidence': 0.5,
                'score': 0.0,
                'last_updated': datetime.now().isoformat(),
                'source': 'default'
            }
    
    def should_trade(self, technical_signal, sentiment=None):
        """Same interface as AlphaVantageSentiment"""
        if sentiment is None:
            sentiment = self.get_gold_sentiment()
        
        signal_sentiment = sentiment['sentiment']
        confidence = sentiment['confidence']
        
        if technical_signal == 'LONG' and signal_sentiment == 'bullish':
            return True, confidence
        elif technical_signal == 'SHORT' and signal_sentiment == 'bearish':
            return True, confidence
        elif signal_sentiment == 'neutral':
            return True, 0.5
        else:
            return False, 0.0
    
    def adjust_position_size(self, base_size, sentiment=None):
        """Same interface as AlphaVantageSentiment"""
        if sentiment is None:
            sentiment = self.get_gold_sentiment()
        
        confidence = sentiment['confidence']
        
        if confidence > 0.8:
            return base_size * 1.3
        elif confidence > 0.6:
            return base_size * 1.1
        elif confidence < 0.4:
            return base_size * 0.7
        else:
            return base_size
