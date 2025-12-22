"""
Simple test script to verify crawler setup and dependencies.
"""

import sys

def check_dependencies():
    """Check if all required dependencies are installed."""
    print("Checking dependencies...\n")

    dependencies = {
        'curl_cffi': 'curl-cffi',
        'bs4': 'beautifulsoup4',
        'lxml': 'lxml',
        'playwright': 'playwright'
    }

    missing = []
    installed = []

    for module, package in dependencies.items():
        try:
            __import__(module)
            installed.append(f"✓ {package}")
        except ImportError:
            missing.append(f"✗ {package}")

    for item in installed:
        print(item)

    if missing:
        print("\nMissing dependencies:")
        for item in missing:
            print(item)
        print("\nInstall missing dependencies with:")
        print("  pip install -r requirements.txt")
        return False

    print("\n✓ All dependencies installed!")
    return True


def check_playwright():
    """Check if Playwright browsers are installed."""
    print("\nChecking Playwright browsers...\n")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("✓ Playwright browsers installed!")
                return True
            except Exception as e:
                if "executable doesn't exist" in str(e).lower() or "not found" in str(e).lower():
                    print("✗ Playwright browsers not installed")
                    print("\nInstall Playwright browsers with:")
                    print("  playwright install")
                    return False
                else:
                    print(f"✗ Error checking Playwright: {e}")
                    return False
    except ImportError:
        print("✗ Playwright not installed")
        return False


def test_basic_functionality():
    """Test basic crawler functionality."""
    print("\nTesting basic functionality...\n")

    try:
        from crawler import WebCrawler

        # Create a crawler instance (don't actually crawl)
        crawler = WebCrawler(
            start_urls=["https://example.com"],
            max_depth=0
        )

        # Test URL normalization
        test_url = "https://example.com/page#fragment"
        normalized = crawler.normalize_url(test_url)
        assert normalized == "https://example.com/page", "URL normalization failed"

        # Test domain checking
        assert crawler.is_allowed_domain("https://example.com/page"), "Domain check failed"

        print("✓ Basic functionality tests passed!")
        return True

    except Exception as e:
        print(f"✗ Functionality test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Crawler Setup Verification")
    print("=" * 60)
    print()

    results = []

    # Check dependencies
    results.append(check_dependencies())

    # Check Playwright
    results.append(check_playwright())

    # Test functionality
    results.append(test_basic_functionality())

    # Summary
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All checks passed! Crawler is ready to use.")
        print("\nTry running:")
        print("  python crawler.py --url https://example.com --max-depth 0")
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
