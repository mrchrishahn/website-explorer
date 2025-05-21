# Website Explorer

A powerful web crawler that efficiently explores websites, captures screenshots, and maintains a structured collection of pages. The crawler is designed to be respectful of website resources and provides real-time progress monitoring through a GUI interface.

## Features

- **Smart Crawling**:
  - Respects robots.txt and implements rate limiting
  - Follows same-domain links only
  - Filters out non-page resources (images, documents, etc.)
  - Limits crawling to 50 pages per domain
  - Handles cookie consent banners and popups automatically

- **Comprehensive Data Collection**:
  - Saves HTML content of each page
  - Takes full-page screenshots
  - Stores metadata about each page
  - Maintains link relationships between pages
  - Creates a structured output directory

- **Real-time Monitoring**:
  - GUI interface showing crawl progress
  - Per-domain progress bars
  - Real-time statistics (pages/second, pending URLs)
  - Estimated completion times
  - Live log display

- **Resource Management**:
  - Concurrent crawling of multiple domains
  - Rate limiting per domain
  - Automatic handling of large websites
  - Efficient resource cleanup

## Requirements

- macOS (tested on macOS 24.1.0)
- Homebrew
- Python 3.13
- Tkinter support
- uv package manager

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd website-explorer
```

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Install all necessary system dependencies
- Create a Python virtual environment
- Install required Python packages
- Set up Playwright browsers
- Create necessary directories
- Create a template domains.csv file

## Usage

1. Edit `domains.csv` with your target domains (one per line):
```csv
example.com
another-domain.com
```

2. Activate the virtual environment:
```bash
source .venv/bin/activate
```

3. Run the crawler:
```bash
python main.py
```

## Output Structure

The crawler creates a structured output in the `crawling_results` directory:

```
crawling_results/
├── domain1.com/
│   ├── page1/
│   │   ├── page.html
│   │   ├── screenshot.png
│   │   └── metadata.json
│   └── page2/
│       ├── page.html
│       ├── screenshot.png
│       └── metadata.json
└── domain2.com/
    └── metadata.json  # For domains with too many pages
```

## Configuration

The crawler can be configured by modifying these parameters in `main.py`:

- `max_pages_per_domain`: Maximum pages to crawl per domain (default: 50)
- `max_concurrent_domains`: Number of domains to crawl simultaneously (default: 5)
- `requests_per_second`: Rate limit per domain (default: 1.0)

## Cookie Banner Handling

The crawler automatically handles common cookie consent banners and popups in multiple languages:
- English: "Accept", "Got it", "Dismiss", etc.
- German: "Akzeptieren", "Zustimmen", "Einverstanden", etc.

## Error Handling

The crawler includes comprehensive error handling for:
- Network issues
- Invalid URLs
- Missing sitemaps
- Resource loading failures
- Screenshot capture issues

## Contributing

Feel free to submit issues and enhancement requests!
