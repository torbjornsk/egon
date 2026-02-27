"""
MRKTedge.ai Web Scraper
Logs in and extracts gold sentiment data from the platform
"""

import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime
from pathlib import Path
import time
import re

class MRKTedgeScraper:
    def __init__(self, credentials_path='config/mrktedge_credentials.json'):
        """Initialize the scraper with login credentials
        
        Args:
            credentials_path: Path to JSON file with email and password
        """
        self.credentials_path = Path(credentials_path)
        self.base_url = "https://www.mrktedge.ai"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.logger = logging.getLogger(__name__)
        self.cache_file = Path("data/mrktedge_cache.json")
        self.cache_duration_minutes = 60
        self.logged_in = False
        
        # Ensure data directory exists
        self.cache_file.parent.mkdir(exist_ok=True)
        
        # Load credentials
        self.credentials = self._load_credentials()
    
    def _load_credentials(self):
        """Load login credentials from file"""
        try:
            with open(self.credentials_path, 'r') as f:
                creds = json.load(f)
            
            if creds.get('email') == 'your_email@example.com':
                self.logger.warning("Please update mrktedge credentials in config/mrktedge_credentials.json")
                return None
            
            return creds
        except Exception as e:
            self.logger.error(f"Error loading credentials: {e}")
            return None
    
    def login(self):
        """Login to mrktedge.ai"""
        if not self.credentials:
            self.logger.error("No valid credentials found")
            return False
        
        try:
            # First, get the login page to extract any CSRF tokens
            login_page = self.session.get(f"{self.base_url}/login", timeout=10)
            
            if login_page.status_code != 200:
                self.logger.error(f"Failed to load login page: {login_page.status_code}")
                return False
            
            # Parse the page to find the login form
            soup = BeautifulSoup(login_page.content, 'html.parser')
            
            # Look for CSRF token (common in modern web apps)
            csrf_token = None
            csrf_input = soup.find('input', {'name': re.compile(r'csrf|token', re.I)})
            if csrf_input:
                csrf_token = csrf_input.get('value')
            
            # Prepare login data
            login_data = {
                'email': self.credentials['email'],
                'password': self.credentials['password']
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Submit login form
            login_response = self.session.post(
                f"{self.base_url}/api/auth/login",  # Common API endpoint
                json=login_data,
                timeout=10
            )
            
            # Check if login was successful
            if login_response.status_code == 200:
                self.logged_in = True
                self.logger.info("Successfully logged in to mrktedge.ai")
                return True
            else:
                self.logger.error(f"Login failed: {login_response.status_code}")
                self.logger.debug(f"Response: {login_response.text[:200]}")
                return False
                
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False
    
    def get_gold_sentiment(self):
        """Get current gold sentiment from mrktedge.ai
        
        Returns:
            dict: {
                'sentiment': 'bullish'|'bearish'|'neutral',
                'confidence': 0.0-1.0,
                'score': -1.0 to 1.0,
                'last_updated': timestamp,
                'source': 'mrktedge',
                'details': {...}  # Additional data from platform
            }
        """
        # Check cache first
        cached = self._load_cache()
        if cached and self._is_cache_valid(cached):
            self.logger.info(f"Using cached mrktedge sentiment: {cached['sentiment']} ({cached['confidence']:.2f})")
            return cached
        
        # Login if not already logged in
        if not self.logged_in:
            if not self.login():
                self.logger.error("Cannot fetch sentiment - login failed")
                return self._neutral_sentiment()
        
        # Fetch fresh sentiment
        try:
            sentiment = self._scrape_sentiment()
            self._save_cache(sentiment)
            return sentiment
        except Exception as e:
            self.logger.error(f"Error scraping sentiment: {e}")
            # Return cached even if expired, or neutral
            return cached if cached else self._neutral_sentiment()
    
    def _scrape_sentiment(self):
        """Scrape sentiment data from mrktedge dashboard"""
        try:
            # Try to fetch the main dashboard
            dashboard_url = f"{self.base_url}/dashboard"
            response = self.session.get(dashboard_url, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Dashboard request failed: {response.status_code}")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for gold/XAUUSD sentiment indicators
            # This is a generic scraper - you'll need to adjust selectors based on actual site structure
            sentiment_data = self._extract_sentiment_from_page(soup)
            
            if not sentiment_data:
                raise Exception("Could not extract sentiment from page")
            
            result = {
                'sentiment': sentiment_data['sentiment'],
                'confidence': sentiment_data['confidence'],
                'score': sentiment_data['score'],
                'last_updated': datetime.now().isoformat(),
                'source': 'mrktedge',
                'details': sentiment_data.get('details', {})
            }
            
            self.logger.info(f"Scraped sentiment: {result['sentiment']} (confidence: {result['confidence']:.2f})")
            return result
            
        except Exception as e:
            self.logger.error(f"Scraping error: {e}")
            raise
    
    def _extract_sentiment_from_page(self, soup):
        """Extract sentiment indicators from the page
        
        This method needs to be customized based on mrktedge.ai's actual HTML structure.
        Common patterns to look for:
        - Sentiment labels (bullish/bearish/neutral)
        - Confidence scores or percentages
        - Color indicators (green=bullish, red=bearish)
        - Bias indicators
        """
        
        # Strategy 1: Look for explicit sentiment text
        sentiment_keywords = {
            'bullish': ['bullish', 'buy', 'long', 'positive', 'uptrend'],
            'bearish': ['bearish', 'sell', 'short', 'negative', 'downtrend'],
            'neutral': ['neutral', 'sideways', 'ranging', 'mixed']
        }
        
        page_text = soup.get_text().lower()
        
        # Search for gold-specific sentiment
        gold_section = None
        for element in soup.find_all(['div', 'section', 'article']):
            text = element.get_text().lower()
            if any(keyword in text for keyword in ['gold', 'xauusd', 'xau/usd']):
                gold_section = element
                break
        
        if not gold_section:
            gold_section = soup  # Use whole page if no specific section found
        
        section_text = gold_section.get_text().lower()
        
        # Count sentiment keywords
        sentiment_scores = {}
        for sentiment, keywords in sentiment_keywords.items():
            score = sum(section_text.count(keyword) for keyword in keywords)
            sentiment_scores[sentiment] = score
        
        # Determine dominant sentiment
        if not any(sentiment_scores.values()):
            # No clear sentiment found
            return {
                'sentiment': 'neutral',
                'confidence': 0.5,
                'score': 0.0,
                'details': {'method': 'default', 'reason': 'no_indicators_found'}
            }
        
        max_sentiment = max(sentiment_scores, key=sentiment_scores.get)
        total_mentions = sum(sentiment_scores.values())
        confidence = sentiment_scores[max_sentiment] / total_mentions if total_mentions > 0 else 0.5
        
        # Convert to score (-1 to 1)
        score_map = {
            'bullish': confidence,
            'bearish': -confidence,
            'neutral': 0.0
        }
        score = score_map[max_sentiment]
        
        # Strategy 2: Look for percentage indicators
        percentages = re.findall(r'(\d+)%', section_text)
        if percentages:
            # If we find percentages, use them to adjust confidence
            avg_pct = sum(int(p) for p in percentages) / len(percentages)
            confidence = min(avg_pct / 100, 1.0)
        
        return {
            'sentiment': max_sentiment,
            'confidence': min(confidence, 1.0),
            'score': score,
            'details': {
                'method': 'keyword_analysis',
                'keyword_counts': sentiment_scores,
                'total_mentions': total_mentions
            }
        }
    
    def _neutral_sentiment(self):
        """Return neutral sentiment"""
        return {
            'sentiment': 'neutral',
            'confidence': 0.5,
            'score': 0.0,
            'last_updated': datetime.now().isoformat(),
            'source': 'mrktedge_default',
            'details': {'reason': 'fallback'}
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
        
        Same interface as AlphaVantageSentiment for compatibility
        """
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
            self.logger.info(f"Skipping {technical_signal} - mrktedge sentiment is {signal_sentiment}")
            return False, 0.0
    
    def adjust_position_size(self, base_size, sentiment=None):
        """Adjust position size based on sentiment confidence
        
        Same interface as AlphaVantageSentiment for compatibility
        """
        if sentiment is None:
            sentiment = self.get_gold_sentiment()
        
        confidence = sentiment['confidence']
        
        if confidence > 0.8:
            multiplier = 1.3
        elif confidence > 0.6:
            multiplier = 1.1
        elif confidence < 0.4:
            multiplier = 0.7
        else:
            multiplier = 1.0
        
        adjusted = base_size * multiplier
        self.logger.debug(f"Position size: {base_size:.3f} -> {adjusted:.3f} (confidence: {confidence:.2f})")
        return adjusted


# Helper function to test the scraper
def test_scraper():
    """Test the mrktedge scraper"""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    scraper = MRKTedgeScraper()
    
    print("\n" + "="*60)
    print("TESTING MRKTEDGE SCRAPER")
    print("="*60)
    
    if not scraper.credentials:
        print("\n⚠️  No credentials found!")
        print("Please update: config/mrktedge_credentials.json")
        return
    
    print(f"\nAttempting login with: {scraper.credentials['email']}")
    
    if scraper.login():
        print("✓ Login successful!")
        
        print("\nFetching gold sentiment...")
        sentiment = scraper.get_gold_sentiment()
        
        print(f"\nSentiment: {sentiment['sentiment'].upper()}")
        print(f"Confidence: {sentiment['confidence']:.2f}")
        print(f"Score: {sentiment['score']:+.2f}")
        print(f"Source: {sentiment['source']}")
        print(f"Details: {sentiment.get('details', {})}")
    else:
        print("✗ Login failed!")
        print("\nTroubleshooting:")
        print("1. Check credentials in config/mrktedge_credentials.json")
        print("2. Verify your mrktedge.ai subscription is active")
        print("3. Check if the site structure has changed")
    
    print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    test_scraper()
