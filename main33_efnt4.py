# --------------------------------
# Imports and Data Classes
# --------------------------------
from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import re

@dataclass
class Business:
    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    email: str = None
    latitude: float = None
    longitude: float = None

@dataclass
class BusinessList:
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        return pd.json_normalize((asdict(business) for business in self.business_list), sep="_")

    def save_to_excel(self, filename):
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

# --------------------------------
# Helper Functions
# --------------------------------
def extract_coordinates_from_url(url: str) -> tuple[float, float]:
    coordinates = url.split('/@')[-1].split('/')[0]
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def extract_email_from_rendered_text(page) -> str:
    """Looks for an email address in the rendered text content."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    visible_text = page.inner_text("body")
    emails = re.findall(email_pattern, visible_text)
    return emails[0] if emails else None

def perform_site_specific_google_search(search_page, website_url) -> str:
    """Performs a Google search for emails on a specific website using the address bar."""
    search_query = f"site:{website_url} email"
    search_page.goto(f"https://www.google.com/search?q={search_query}")
    search_page.wait_for_timeout(3000)  # Wait for search results to load

    try:
        # Extract email from search results page
        return extract_email_from_rendered_text(search_page)
    except Exception as e:
        print(f"Error during Google search: {e}")
        return None

def search_email_on_website(context, website_url) -> str:
    """Attempts to find an email on the boutique's website, with a fallback Google search if none found."""
    search_page = context.new_page()
    common_contact_paths = ["/about", "/contact", "/about-us", "/contact-us", "/support", "/help", "/get-in-touch"]

    try:
        # Step 1: Check the main page for an email
        print(f"Visiting main page: {website_url}")
        search_page.goto(website_url, timeout=30000)
        search_page.wait_for_timeout(2000)  # Wait for page load
        email_found = extract_email_from_rendered_text(search_page)
        if email_found:
            print(f"Email found directly on {website_url}: {email_found}")
            return email_found

        # Step 2: Check common contact paths if no email found on the main page
        for path in common_contact_paths:
            try:
                # Construct the full URL for each common path and print it
                full_url = f"{website_url.rstrip('/')}{path}"
                print(f"Attempting to visit: {full_url}")
                search_page.goto(full_url, timeout=15000)
                search_page.wait_for_timeout(2000)  # Wait for page load
                email_found = extract_email_from_rendered_text(search_page)
                if email_found:
                    print(f"Email found on {full_url}: {email_found}")
                    return email_found
            except Exception as e:
                print(f"Failed to load {full_url}: {e}")
        
        # Step 3: If no email found, perform a Google search as a fallback
        print(f"No email found on {website_url}. Performing Google search with site-specific query.")
        email_found = perform_site_specific_google_search(search_page, website_url)
        return email_found

    finally:
        search_page.close()  # Ensure the tab is closed after search

def is_valid_url(url: str) -> bool:
    """Checks if the URL has a valid domain format."""
    url_pattern = r"^(http:\/\/www\.|https:\/\/www\.|http:\/\/|https:\/\/)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"
    return re.match(url_pattern, url) is not None

# --------------------------------
# Main Function
# --------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()

    search_list = [args.search] if args.search else []
    total = args.total if args.total else 1_000_000

    if not args.search:
        input_file_path = os.path.join(os.getcwd(), 'input.txt')
        if os.path.exists(input_file_path):
            with open(input_file_path, 'r') as file:
                search_list = file.readlines()
        if len(search_list) == 0:
            print('Error: You must pass a search argument or add searches to input.txt')
            sys.exit()

    # --------------------------------
    # Playwright Browser Setup
    # --------------------------------
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()  # Create a context for multiple tabs
        page = context.new_page()  # Original Google Maps page
        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(5000)
        
        # Loop over each search term
        for search_for in search_list:
            print(f"Searching for: {search_for.strip()}")
            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(3000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')
            listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
            listings = [listing.locator("xpath=..") for listing in listings]
            business_list = BusinessList()

            # --------------------------------
            # Extract Business Details
            # --------------------------------
            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(5000)

                    business = Business()
                    business.name = page.locator('//h1[contains(@Class, "DUwDvf lfPIob")]').inner_text() or ""
                    business.address = page.locator('//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]').inner_text() or ""
                    business.website = page.locator('//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]').inner_text() or ""
                    business.phone_number = page.locator('//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]').inner_text() or ""
                    business.latitude, business.longitude = extract_coordinates_from_url(page.url)

                    # --------------------------------
                    # Website and Email Extraction
                    # --------------------------------
                    if business.website:
                        # Add protocol if missing
                        if not business.website.startswith(('http://', 'https://')):
                            business.website = f"https://{business.website}"
                        
                        print(f"Extracted website URL: {business.website}")

                        # Validate URL format and attempt to find email
                        if is_valid_url(business.website):
                            business.email = search_email_on_website(context, business.website)
                        else:
                            print(f"Invalid URL skipped: {business.website}")
                    
                    business_list.business_list.append(business)
                except Exception as e:
                    print(f"Error extracting business details: {e}")

            # --------------------------------
            # Save Results
            # --------------------------------
            business_list.save_to_excel(f"google_maps_data_{search_for.strip().replace(' ', '_')}")
            business_list.save_to_csv(f"google_maps_data_{search_for.strip().replace(' ', '_')}")

        browser.close()

if __name__ == "__main__":
    main()
