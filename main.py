import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
from collections import defaultdict
import time
import logging
import os
from playwright.async_api import async_playwright
import hashlib
import json
import asyncio
import aiohttp
import aiofiles
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional
import random
import threading
from gui import CrawlerGUI, GUILogHandler

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common selectors for cookie consent banners and popups
COOKIE_BANNER_SELECTORS = [
    # Common cookie consent buttons
    '[aria-label*="cookie" i] button',
    '[aria-label*="consent" i] button',
    '[aria-label*="accept" i] button',
    '[aria-label*="agree" i] button',
    '[aria-label*="got it" i] button',
    '[aria-label*="dismiss" i] button',
    '[aria-label*="cookies" i] button',
    '[aria-label*="zustimmen" i] button',
    '[aria-label*="akzeptieren" i] button',
    '[aria-label*="einverstanden" i] button',
    # Common cookie banner classes
    '.cookie-banner button',
    '.cookie-consent button', 
    '.cookie-notice button',
    '.cookie-popup button',
    '.cookie-dialog button',
    '.cookie-bar button',
    '.cookie-warning button',
    '.cookie-alert button',
    '.cookie-hinweis button',
    '.cookie-zustimmung button',
    '.datenschutz-banner button',
    # Common cookie banner IDs
    '#cookie-banner button',
    '#cookie-consent button',
    '#cookie-notice button', 
    '#cookie-popup button',
    '#cookie-dialog button',
    '#cookie-bar button',
    '#cookie-warning button',
    '#cookie-alert button',
    '#cookie-hinweis button',
    '#datenschutz-banner button',
    # Common button text
    'button:has-text("Accept")',
    'button:has-text("Accept All")',
    'button:has-text("Accept Cookies")',
    'button:has-text("I Accept")',
    'button:has-text("I Agree")',
    'button:has-text("Got it")',
    'button:has-text("Dismiss")',
    'button:has-text("Close")',
    'button:has-text("Akzeptieren")',
    'button:has-text("Alle akzeptieren")',
    'button:has-text("Cookies akzeptieren")',
    'button:has-text("Ich akzeptiere")',
    'button:has-text("Einverstanden")',
    'button:has-text("Zustimmen")',
    'button:has-text("Verstanden")',
    'button:has-text("Schließen")',
    # Common popup close buttons
    '.popup-close',
    '.modal-close', 
    '.dialog-close',
    '.banner-close',
    '.hinweis-close',
    '[aria-label="Close"]',
    '[aria-label="Dismiss"]',
    '[aria-label="Schließen"]',
    '[aria-label="Ausblenden"]',
]

class DomainStats:
    def __init__(self):
        self.pages_crawled = 0
        self.total_links = 0
        self.start_time = datetime.now()
        self.last_update = datetime.now()
        self.pending_urls = set()
        self.page_times = []  # List to store timestamps of last 100 pages
        self.max_page_history = 100  # Number of pages to keep in history
        self.screenshot_failures = 0  # Track number of screenshot failures
        self.max_screenshot_failures = 5  # Maximum allowed failures before abandoning domain

    def update(self, new_links: int = 0):
        self.pages_crawled += 1
        self.total_links += new_links
        now = datetime.now()
        
        # Add current page time to history
        self.page_times.append(now)
        
        # Keep only the last max_page_history pages
        if len(self.page_times) > self.max_page_history:
            self.page_times = self.page_times[-self.max_page_history:]
        
        self.last_update = now

    def get_elapsed_time(self) -> float:
        return (self.last_update - self.start_time).total_seconds()

    def get_pages_per_second(self) -> float:
        """Calculate pages per second based on the last max_page_history pages."""
        if len(self.page_times) < 2:
            return 0.0
            
        # Calculate time difference between first and last page in history
        time_diff = (self.page_times[-1] - self.page_times[0]).total_seconds()
        if time_diff == 0:
            return 0.0
            
        # Calculate pages per second based on the number of pages in history
        return (len(self.page_times) - 1) / time_diff

    def get_estimated_completion_time(self) -> datetime:
        if not self.pending_urls:
            return datetime.now()
        
        # Get current pages per second rate
        pages_per_second = self.get_pages_per_second()
        if pages_per_second == 0:
            return datetime.now()
        
        # Calculate remaining pages (considering the page limit)
        remaining_pages = min(len(self.pending_urls), 50 - self.pages_crawled)
        
        # Calculate estimated seconds remaining
        estimated_seconds = remaining_pages / pages_per_second
        
        return datetime.now() + timedelta(seconds=estimated_seconds)

    def get_progress_percentage(self) -> float:
        return min(100.0, (self.pages_crawled / 50) * 100)

    def should_abandon_domain(self) -> bool:
        """Check if we should abandon the domain due to too many screenshot failures."""
        return self.screenshot_failures >= self.max_screenshot_failures

class GlobalStats:
    def __init__(self, message_queue=None):
        self.start_time = datetime.now()
        self.total_pages_crawled = 0
        self.total_pending_urls = 0
        self.domain_stats: Dict[str, DomainStats] = {}
        self.message_queue = message_queue
        self.page_times = []  # List to store timestamps of last 100 pages across all domains
        self.max_page_history = 100  # Number of pages to keep in history

    def update(self, domain: str, stats: DomainStats):
        self.domain_stats[domain] = stats
        self.total_pages_crawled = sum(s.pages_crawled for s in self.domain_stats.values())
        self.total_pending_urls = sum(len(s.pending_urls) for s in self.domain_stats.values())
        
        # Add current page time to global history
        self.page_times.append(datetime.now())
        if len(self.page_times) > self.max_page_history:
            self.page_times = self.page_times[-self.max_page_history:]
        
        if self.message_queue:
            # Update domain progress
            self.message_queue.put({
                'type': 'domain_progress',
                'domain': domain,
                'stats': {
                    'progress_percentage': stats.get_progress_percentage(),
                    'pages_crawled': stats.pages_crawled,
                    'pending_urls': len(stats.pending_urls),
                    'pages_per_second': stats.get_pages_per_second()
                }
            })
            
            # Update global stats
            self.message_queue.put({
                'type': 'global_stats',
                'stats': {
                    'total_pages_crawled': self.total_pages_crawled,
                    'total_pending_urls': self.total_pending_urls,
                    'elapsed_time': str(timedelta(seconds=int(self.get_elapsed_time()))),
                    'estimated_time_remaining': str(self.get_estimated_completion_time() - datetime.now())
                }
            })

    def get_elapsed_time(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def get_pages_per_second(self) -> float:
        """Calculate global pages per second based on the last max_page_history pages."""
        if len(self.page_times) < 2:
            return 0.0
            
        # Calculate time difference between first and last page in history
        time_diff = (self.page_times[-1] - self.page_times[0]).total_seconds()
        if time_diff == 0:
            return 0.0
            
        # Calculate pages per second based on the number of pages in history
        return (len(self.page_times) - 1) / time_diff

    def get_estimated_completion_time(self) -> datetime:
        if not self.domain_stats:
            return datetime.now()
        
        # Get global pages per second rate
        pages_per_second = self.get_pages_per_second()
        if pages_per_second == 0:
            return datetime.now()
        
        # Calculate total remaining pages across all domains
        total_remaining = 0
        for domain, stats in self.domain_stats.items():
            remaining = min(len(stats.pending_urls), 50 - stats.pages_crawled)
            total_remaining += remaining
        
        # Calculate estimated seconds remaining
        estimated_seconds = total_remaining / pages_per_second
        
        return datetime.now() + timedelta(seconds=estimated_seconds)

    def log_status(self):
        elapsed = self.get_elapsed_time()
        estimated_completion = self.get_estimated_completion_time()
        time_remaining = estimated_completion - datetime.now()
        
        # logging.info("\n=== Global Crawling Status ===")
        # logging.info(f"Total pages crawled: {self.total_pages_crawled}")
        # logging.info(f"Total pending URLs: {self.total_pending_urls}")
        # logging.info(f"Elapsed time: {timedelta(seconds=int(elapsed))}")
        # logging.info(f"Estimated time remaining: {time_remaining}")
        # logging.info("\nPer-domain status:")
        
        # for domain, stats in self.domain_stats.items():
        #     logging.info(f"\n{domain}:")
        #     logging.info(f"  Pages crawled: {stats.pages_crawled}/50 ({stats.get_progress_percentage():.1f}%)")
        #     logging.info(f"  Pending URLs: {len(stats.pending_urls)}")
        #     logging.info(f"  Pages/second: {stats.get_pages_per_second():.2f}")
        #     logging.info(f"  Estimated completion: {stats.get_estimated_completion_time().strftime('%H:%M:%S')}")
        
        # logging.info("\n===========================")

class DomainRateLimiter:
    def __init__(self, requests_per_second: float = 1.0):
        self.requests_per_second = requests_per_second
        self.last_request_time: Dict[str, datetime] = {}
        self.lock = asyncio.Lock()

    async def acquire(self, domain: str):
        async with self.lock:
            now = datetime.now()
            if domain in self.last_request_time:
                time_since_last = (now - self.last_request_time[domain]).total_seconds()
                if time_since_last < 1.0 / self.requests_per_second:
                    await asyncio.sleep(1.0 / self.requests_per_second - time_since_last)
            self.last_request_time[domain] = datetime.now()

class WebsiteCrawler:
    def __init__(self, domains: List[str], gui: CrawlerGUI, max_pages_per_domain: int = 50, max_concurrent_domains: int = 5, requests_per_second: float = 1.0):
        self.domains = domains
        self.max_pages_per_domain = max_pages_per_domain
        self.max_concurrent_domains = max_concurrent_domains
        self.requests_per_second = requests_per_second
        self.visited_urls: Dict[str, Set[str]] = {}  # domain -> set of visited URLs
        self.domain_stats: Dict[str, DomainStats] = {}
        self.gui = gui
        self.global_stats = GlobalStats(gui.message_queue)
        self.setup_logging()
        
        # Initialize visited URLs sets for each domain
        for domain in domains:
            self.visited_urls[domain] = set()
            self.domain_stats[domain] = DomainStats()
        self.page_links: Dict[str, Set[str]] = defaultdict(set)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.base_output_dir = "crawling_results"
        self.playwright = None
        self.browser = None
        self.rate_limiter = DomainRateLimiter()
        self.domain_semaphores = {}  # Semaphores for domain concurrency control
        self.status_update_task = None
        self.session = None
        self.abandoned_domains = set()  # Track domains we've abandoned
        self.domain_tasks = {}  # Track active tasks per domain
        self.domain_locks = {}  # Locks for domain operations
        self.domain_stop_events = {}  # Stop events for each domain
        
        # File extensions to ignore
        self.ignored_extensions = {
            # Images
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico',
            # Documents
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            # Archives
            '.zip', '.rar', '.7z', '.tar', '.gz',
            # Media
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
            # Other
            '.css', '.js', '.json', '.txt', '.csv'
        }

    def setup_logging(self):
        """Set up logging configuration."""
        # Remove any existing handlers
        for handler in logging.getLogger().handlers[:]:
            logging.getLogger().removeHandler(handler)
        
        # Set up basic logging configuration
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Add GUI handler
        gui_handler = GUILogHandler(self.gui.message_queue)
        gui_handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(gui_handler)
        
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Add file handler
        file_handler = logging.FileHandler('logs/crawler.log')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)

    async def initialize(self):
        """Initialize Playwright and browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)  # Allow up to 100 concurrent connections
        )

    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def get_domain_stats(self, domain: str) -> DomainStats:
        """Get or create stats for a domain."""
        if domain not in self.domain_stats:
            self.domain_stats[domain] = DomainStats()
        return self.domain_stats[domain]

    def should_continue_crawling(self, domain: str) -> bool:
        """Check if we should continue crawling a domain based on page limit."""
        stats = self.get_domain_stats(domain)
        return stats.pages_crawled < self.max_pages_per_domain

    def log_domain_stats(self, domain: str):
        """Log current statistics for a domain."""
        stats = self.get_domain_stats(domain)
        logging.info(
            f"Domain {domain} stats: "
            f"Pages crawled: {stats.pages_crawled}/{self.max_pages_per_domain}, "
            f"Total links: {stats.total_links}, "
            f"Pages/second: {stats.get_pages_per_second():.2f}"
        )

    def get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create a semaphore for a domain."""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(self.max_concurrent_domains)
        return self.domain_semaphores[domain]

    async def handle_popups(self, page):
        """Handle cookie banners and popups."""
        try:
            # Wait for any dynamic content to load
            await page.wait_for_load_state('networkidle')
            
            # Try each selector
            for selector in COOKIE_BANNER_SELECTORS:
                try:
                    # Check if element exists and is visible
                    element = await page.query_selector(selector)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            # Click the element
                            await element.click()
                            logging.info(f"Dismissed popup using selector: {selector}")
                            # Wait a bit for the popup to disappear
                            await asyncio.sleep(0.5)
                except Exception as e:
                    continue  # Try next selector if this one fails
            
            # Additional check for iframes (some cookie banners are in iframes)
            frames = page.frames
            for frame in frames:
                for selector in COOKIE_BANNER_SELECTORS:
                    try:
                        element = await frame.query_selector(selector)
                        if element:
                            is_visible = await element.is_visible()
                            if is_visible:
                                await element.click()
                                logging.info(f"Dismissed popup in iframe using selector: {selector}")
                                await asyncio.sleep(0.5)
                    except Exception as e:
                        continue
            
        except Exception as e:
            logging.warning(f"Error handling popups: {str(e)}")

    async def save_page_content(self, url: str, html_content: str, domain: str):
        """Save the HTML content of a page."""
        try:
            dir_path = self.get_url_directory(url, domain)
            html_path = os.path.join(dir_path, 'page.html')
            
            async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
                await f.write(html_content)
            
            logging.info(f"HTML content saved: {html_path}")
            return html_path
        except Exception as e:
            logging.error(f"Failed to save HTML content for {url}: {str(e)}")
            return None

    def get_domain_lock(self, domain: str) -> asyncio.Lock:
        """Get or create a lock for a domain."""
        if domain not in self.domain_locks:
            self.domain_locks[domain] = asyncio.Lock()
        return self.domain_locks[domain]

    def get_domain_stop_event(self, domain: str) -> asyncio.Event:
        """Get or create a stop event for a domain."""
        if domain not in self.domain_stop_events:
            self.domain_stop_events[domain] = asyncio.Event()
        return self.domain_stop_events[domain]

    async def abandon_domain(self, domain: str, failure_count: int):
        """Safely abandon a domain and stop all operations."""
        if domain in self.abandoned_domains:
            return  # Already abandoned
            
        logging.warning(f"Abandoning domain {domain} due to {failure_count} screenshot failures")
        self.abandoned_domains.add(domain)
        
        # Set the stop event for this domain
        stop_event = self.get_domain_stop_event(domain)
        stop_event.set()
        
        # Clear all pending URLs for the domain
        stats = self.get_domain_stats(domain)
        stats.pending_urls.clear()
        
        # Save abandonment metadata
        await self.save_domain_abandonment_metadata(domain, failure_count)

    async def take_screenshot(self, url: str, domain: str):
        """Take a screenshot of the given URL."""
        try:
            dir_path = self.get_url_directory(url, domain)
            screenshot_path = os.path.join(dir_path, 'screenshot.png')
            
            # Skip if screenshot already exists
            if os.path.exists(screenshot_path):
                return screenshot_path

            # Check if domain has been abandoned
            if domain in self.abandoned_domains:
                logging.info(f"Skipping screenshot for abandoned domain: {domain}")
                return None

            # Create a new page and navigate to URL
            page = await self.browser.new_page()
            try:
                await page.goto(url, wait_until='networkidle', timeout=10000)
                
                # Handle popups before taking screenshot
                await self.handle_popups(page)
                
                # Take full page screenshot
                await page.screenshot(path=screenshot_path, full_page=True)
                logging.info(f"Screenshot saved: {screenshot_path}")
                return screenshot_path
            except Exception as e:
                # Increment failure counter
                stats = self.get_domain_stats(domain)
                stats.screenshot_failures += 1
                
                # Check if we should abandon the domain
                if stats.should_abandon_domain():
                    await self.abandon_domain(domain, stats.screenshot_failures)
                
                logging.error(f"Failed to take screenshot of {url}: {str(e)}")
                return None
            finally:
                await page.close()
        except Exception as e:
            logging.error(f"Failed to take screenshot of {url}: {str(e)}")
            return None

    async def save_domain_abandonment_metadata(self, domain: str, failure_count: int):
        """Save metadata about why a domain was abandoned."""
        try:
            domain_dir = os.path.join(self.base_output_dir, domain)
            os.makedirs(domain_dir, exist_ok=True)
            
            metadata = {
                'domain': domain,
                'timestamp': datetime.now().isoformat(),
                'reason': 'Too many screenshot failures',
                'failure_count': failure_count,
                'max_allowed_failures': self.domain_stats[domain].max_screenshot_failures,
                'pages_crawled_before_abandonment': self.domain_stats[domain].pages_crawled
            }
            
            metadata_path = os.path.join(domain_dir, 'abandonment_metadata.json')
            async with aiofiles.open(metadata_path, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logging.info(f"Saved abandonment metadata for {domain}")
        except Exception as e:
            logging.error(f"Failed to save abandonment metadata for {domain}: {str(e)}")

    async def save_page_metadata(self, url: str, domain: str, links: Set[str]):
        """Save metadata about the page including its links."""
        try:
            dir_path = self.get_url_directory(url, domain)
            metadata_path = os.path.join(dir_path, 'metadata.json')
            
            metadata = {
                'url': url,
                'domain': domain,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'links': list(links)
            }
            
            async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logging.info(f"Metadata saved: {metadata_path}")
            return metadata_path
        except Exception as e:
            logging.error(f"Failed to save metadata for {url}: {str(e)}")
            return None

    async def start_status_updates(self):
        """Start periodic status updates."""
        while True:
            self.global_stats.log_status()
            await asyncio.sleep(30)  # Update every 30 seconds

    async def check_domain_size(self, domain: str) -> bool:
        """Check if a domain has more than max_pages_per_domain pages in its sitemap."""
        try:
            sitemap_urls = await self.get_sitemap_urls(domain)
            if len(sitemap_urls) > self.max_pages_per_domain:
                # Create metadata directory for the domain
                domain_dir = os.path.join(self.base_output_dir, domain)
                os.makedirs(domain_dir, exist_ok=True)
                
                # Save metadata about why we skipped this domain
                metadata = {
                    'domain': domain,
                    'timestamp': datetime.now().isoformat(),
                    'reason': 'Too many pages in sitemap',
                    'page_count': len(sitemap_urls),
                    'max_pages': self.max_pages_per_domain
                }
                
                metadata_path = os.path.join(domain_dir, 'metadata.json')
                async with aiofiles.open(metadata_path, 'w') as f:
                    await f.write(json.dumps(metadata, indent=2))
                
                logging.info(f"Skipping domain {domain}: {len(sitemap_urls)} pages found in sitemap (max: {self.max_pages_per_domain})")
                return False
            return True
        except Exception as e:
            logging.error(f"Error checking domain size for {domain}: {str(e)}")
            return True  # Continue crawling if we can't determine size

    def is_valid_page_url(self, url: str) -> bool:
        """Check if a URL is a valid page URL (not a resource)."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            
            # Check for ignored file extensions
            if any(path.endswith(ext) for ext in self.ignored_extensions):
                return False
            
            # Check for common resource patterns
            if any(pattern in path for pattern in ['/static/', '/assets/', '/media/', '/images/', '/img/', '/css/', '/js/']):
                return False
            
            # Check for query parameters that indicate resources
            query = parsed.query.lower()
            if any(param in query for param in ['format=', 'type=', 'download=', 'file=']):
                return False
            
            return True
        except:
            return False

    def has_page_been_crawled(self, url: str, domain: str) -> bool:
        """Check if a page has already been crawled by checking its directory contents."""
        try:
            dir_path = self.get_url_directory(url, domain)
            
            # Check if directory exists
            if not os.path.exists(dir_path):
                return False
                
            # Check for required files
            required_files = ['page.html', 'screenshot.png', 'metadata.json']
            existing_files = os.listdir(dir_path)
            
            # Check if all required files exist and are not empty
            for required_file in required_files:
                file_path = os.path.join(dir_path, required_file)
                if required_file not in existing_files or os.path.getsize(file_path) == 0:
                    return False
            
            # Verify metadata file contains valid data
            metadata_path = os.path.join(dir_path, 'metadata.json')
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    if not all(key in metadata for key in ['url', 'domain', 'timestamp', 'links']):
                        return False
            except (json.JSONDecodeError, KeyError):
                return False
            
            logging.info(f"Page already crawled: {url}")
            return True
            
        except Exception as e:
            logging.warning(f"Error checking if page was crawled: {str(e)}")
            return False

    async def crawl_page(self, domain: str, url: str, depth: int = 0) -> Optional[Dict]:
        """Crawl a single page and return its data."""
        # Early check for abandoned domain
        if domain in self.abandoned_domains:
            return None

        # Check stop event
        stop_event = self.get_domain_stop_event(domain)
        if stop_event.is_set():
            return None

        if depth > 10:  # Maximum depth to prevent infinite recursion
            return None
            
        # Check if we've already visited this URL
        if url in self.visited_urls[domain]:
            logging.debug(f"Skipping already visited URL: {url}")
            return None
            
        # Early validation of URL to prevent crawling non-HTML resources
        if not self.is_valid_page_url(url):
            logging.debug(f"Skipping non-HTML resource: {url}")
            self.visited_urls[domain].add(url)  # Mark as visited to prevent future attempts
            return None
            
        # Check if page has already been crawled
        if self.has_page_been_crawled(url, domain):
            # Add to visited URLs to prevent future attempts
            self.visited_urls[domain].add(url)
            # Update stats to reflect the existing page
            stats = self.get_domain_stats(domain)
            stats.pages_crawled += 1
            self.global_stats.update(domain, stats)
            return None
            
        # Mark URL as visited
        self.visited_urls[domain].add(url)
        
        # Check if we've reached the page limit for this domain
        if self.domain_stats[domain].pages_crawled >= self.max_pages_per_domain:
            logging.info(f"Reached page limit for {domain}")
            return None

        try:
            stats = self.get_domain_stats(domain)
            stats.pending_urls.discard(url)  # Remove from pending as we're processing it
            
            logging.info(f"Crawling: {url} ({stats.pages_crawled + 1}/{self.max_pages_per_domain})")

            # Get domain semaphore and rate limiter
            semaphore = self.get_domain_semaphore(domain)
            
            async with semaphore:
                # Check stop event again after acquiring semaphore
                if stop_event.is_set():
                    return None
                    
                await self.rate_limiter.acquire(domain)
                
                async with self.session.get(url, allow_redirects=True) as response:
                    # Check stop event before processing response
                    if stop_event.is_set():
                        return None

                    if response.status != 200:
                        logging.warning(f"Failed to fetch {url}: Status {response.status}")
                        return None
                    # Check content type before processing
                    content_type = response.headers.get('Content-Type', '').lower()
                    if not content_type.startswith('text/html'):
                        logging.debug(f"Skipping non-HTML content type: {content_type} for {url}")
                        return None
                    html_content = await response.text()
                    
                    # Check stop event before saving content
                    if stop_event.is_set():
                        return None
                    
                    # Save HTML content
                    await self.save_page_content(url, html_content, domain)
                    
                    # Take screenshot
                    await self.take_screenshot(url, domain)
                    
                    # Check stop event before processing links
                    if stop_event.is_set():
                        return None
                    
                    soup = BeautifulSoup(html_content, 'html.parser')
                    page_links = set()
                    
                    # Extract links
                    links = []
                    for link in soup.find_all('a', href=True):
                        # Check stop event during link processing
                        if stop_event.is_set():
                            return None
                            
                        href = link['href']
                        absolute_url = urljoin(url, href)
                        parsed_url = urlparse(absolute_url)
                        
                        # Only follow links from the same domain
                        if parsed_url.netloc == domain:
                            # Normalize URL to prevent duplicates with different formats
                            normalized_url = self.normalize_url(absolute_url)
                            if normalized_url not in self.visited_urls[domain]:
                                links.append(normalized_url)
                                self.page_links[url].add(normalized_url)
                                stats.pending_urls.add(normalized_url)  # Add to pending queue
                                # Create a task for the new URL
                                asyncio.create_task(self.crawl_page(domain, normalized_url, depth + 1))
                    
                    # Update stats
                    stats.update(len(links))
                    self.global_stats.update(domain, stats)
                    
                    # Save page metadata
                    await self.save_page_metadata(url, domain, links)
                    
                    return {
                        'url': url,
                        'domain': domain,
                        'links': links,
                        'pages_crawled': stats.pages_crawled,
                        'total_links': stats.total_links
                    }
        except aiohttp.ClientError as e:
            logging.error(f"Network error crawling {url}: {str(e)}")
        except Exception as e:
            logging.error(f"Error crawling {url}: {str(e)}")
            return None

    def normalize_url(self, url: str) -> str:
        """Normalize URL to prevent duplicates with different formats."""
        # Remove trailing slashes
        url = url.rstrip('/')
        
        # Remove default ports
        parsed = urlparse(url)
        if parsed.port in (80, 443):
            netloc = parsed.netloc.split(':')[0]
            url = url.replace(parsed.netloc, netloc)
        
        # Remove fragments
        url = url.split('#')[0]
        
        # Convert to lowercase
        url = url.lower()
        
        return url

    async def crawl_domain(self, domain: str):
        """Crawl a domain starting from its sitemap and following same-domain links."""
        logging.info(f"Starting crawl for domain: {domain}")
        
        # Initialize stop event for this domain
        self.get_domain_stop_event(domain)
        
        # First check if the domain is too large
        if not await self.check_domain_size(domain):
            return
        
        # Then try to get URLs from sitemap
        sitemap_urls = await self.get_sitemap_urls(domain)
        
        # If no sitemap found, start from homepage
        if not sitemap_urls:
            sitemap_urls = {f"https://{domain}"}
        
        # Add initial URLs to pending queue
        stats = self.get_domain_stats(domain)
        stats.pending_urls.update(sitemap_urls)
        
        # Create tasks for all sitemap URLs
        tasks = []
        for url in sitemap_urls:
            if self.is_same_domain(url, domain) and self.should_continue_crawling(domain):
                task = asyncio.create_task(self.crawl_page(domain, url))
                tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log final stats
        self.global_stats.update(domain, stats)
        self.global_stats.log_status()

    async def get_sitemap_urls(self, domain: str) -> Set[str]:
        """Try to find and parse sitemap.xml for the given domain."""
        sitemap_urls = set()
        try:
            # Try common sitemap locations
            sitemap_locations = [
                f"https://{domain}/sitemap.xml",
                f"https://{domain}/sitemap_index.xml",
                f"https://{domain}/sitemap/sitemap.xml"
            ]
            
            for sitemap_url in sitemap_locations:
                try:
                    async with self.session.get(sitemap_url) as response:
                        if response.status == 200:
                            content = await response.text()
                            try:
                                root = ET.fromstring(content)
                                # Handle both sitemap index and regular sitemaps
                                if 'sitemapindex' in root.tag:
                                    # This is a sitemap index
                                    for sitemap in root.findall('.//{*}loc'):
                                        sitemap_urls.update(await self.get_sitemap_urls_from_index(sitemap.text))
                                else:
                                    # This is a regular sitemap
                                    for url in root.findall('.//{*}loc'):
                                        sitemap_urls.add(url.text)
                            except ET.ParseError:
                                logging.warning(f"Failed to parse sitemap at {sitemap_url}")
                                continue
                except Exception as e:
                    logging.error(f"Error fetching sitemap {sitemap_url}: {str(e)}")
                    continue
        except Exception as e:
            logging.error(f"Error processing sitemaps for {domain}: {str(e)}")
        
        return sitemap_urls

    async def get_sitemap_urls_from_index(self, sitemap_url: str) -> Set[str]:
        """Parse individual sitemap from sitemap index."""
        urls = set()
        try:
            async with self.session.get(sitemap_url) as response:
                if response.status == 200:
                    content = await response.text()
                    root = ET.fromstring(content)
                    for url in root.findall('.//{*}loc'):
                        urls.add(url.text)
        except Exception as e:
            logging.error(f"Error fetching sitemap from index {sitemap_url}: {str(e)}")
        return urls

    def get_url_directory(self, url: str, domain: str) -> str:
        """Create a directory structure for a URL."""
        # Create a safe directory name from the URL
        url_path = urlparse(url).path
        if not url_path or url_path == '/':
            url_path = 'index'
        else:
            # Remove leading/trailing slashes and replace remaining with underscores
            url_path = url_path.strip('/').replace('/', '_')
        
        # Create the full path
        full_path = os.path.join(self.base_output_dir, domain, url_path)
        os.makedirs(full_path, exist_ok=True)
        return full_path

    def is_same_domain(self, url: str, base_domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed_url = urlparse(url)
            return parsed_url.netloc == base_domain
        except:
            return False

    async def save_results(self, output_file: str):
        """Save the crawling results to a CSV file."""
        async with aiofiles.open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            await f.write('Source URL,Target URL,Content Directory,Domain,Pages Crawled,Total Links\n')
            for source, targets in self.page_links.items():
                domain = urlparse(source).netloc
                content_dir = self.get_url_directory(source, domain)
                stats = self.get_domain_stats(domain)
                for target in targets:
                    await f.write(f'{source},{target},{content_dir},{domain},{stats.pages_crawled},{stats.total_links}\n')

async def main():
    # Read domains from input CSV
    input_file = 'domains.csv'
    output_file = 'crawl_results.csv'
    
    # Create GUI
    gui = CrawlerGUI()
    
    try:
        # Read domains first
        domains = []
        async with aiofiles.open(input_file, 'r') as f:
            async for line in f:
                domain = line.strip()
                if domain:
                    domains.append(domain)
        
        if not domains:
            logging.error("No domains found in input file")
            return
        
        # Create crawler with domains and GUI
        crawler = WebsiteCrawler(domains=domains, gui=gui, max_pages_per_domain=50)
        
        # Initialize Playwright
        await crawler.initialize()
        
        # Start status update task
        crawler.status_update_task = asyncio.create_task(crawler.start_status_updates())
        
        # Create tasks for each domain
        tasks = [crawler.crawl_domain(domain) for domain in domains]
        
        # Add GUI update task
        tasks.append(gui.run_async())
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks)
        
        # Cancel status update task
        if crawler.status_update_task:
            crawler.status_update_task.cancel()
            try:
                await crawler.status_update_task
            except asyncio.CancelledError:
                pass
        
        # Save results
        await crawler.save_results(output_file)
        logging.info(f"Crawling completed. Results saved to {output_file}")
        
    except FileNotFoundError:
        logging.error(f"Input file {input_file} not found")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
    finally:
        # Cleanup Playwright resources
        if 'crawler' in locals():
            await crawler.cleanup()
        
        # Close GUI
        gui.close()

if __name__ == "__main__":
    asyncio.run(main())
