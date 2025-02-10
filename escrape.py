# --------------------------------
# Imports and Data Classes
# --------------------------------
from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
from pathlib import Path
import pandas as pd
import os
import re
import requests
import json
import random


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

def perform_site_specific_google_search(search_page, website_url: str) -> str:
    """
    Performs a Google search for emails on a specific website using the address bar.
    Returns the first email found or None if no email is present.
    """
    # Validate the website URL
    if not website_url.startswith(("http://", "https://")):
        print(f"Invalid website URL: {website_url}")
        return None

    try:
        # Construct the site-specific query
        search_query = f"site:{website_url} email"
        search_page.goto(f"https://www.google.com/search?q={search_query}", timeout=15000)  # Increased timeout

        # Wait for the search results container to load
        search_page.wait_for_selector('//div[@id="search"]', timeout=5000)  # Ensures the results container is present

        # Extract email from the rendered text of the search results
        email_found = extract_email_from_rendered_text(search_page)
        if email_found:
            print(f"Email found via Google search for {website_url}: {email_found}")
            return email_found
        else:
            print(f"No email found via Google search for {website_url}.")
            return None

    except TimeoutError:
        print(f"Timeout while searching for {website_url}. Check network connection or website availability.")
        return None

    except Exception as e:
        print(f"Error during Google search for {website_url}: {e}")
        return None



def search_email_on_website(local_context, website_url,proxy_context) -> str:
    """Attempts to find an email on the boutique's website, with a fallback Google search if none found."""
    search_page = local_context.new_page()
    common_contact_paths = ["/about", "/contact", "/about-us", "/contact-us", "/support", "/help", "/get-in-touch"]

    try:
        # Step 1: Check the main page for an email
        print(f"Visiting main page: {website_url}")
        #search_page.goto(website_url, timeout=31234)
        #search_page.wait_for_timeout(2000)  # Wait for page load
        #use the following two lines as i don't need to be sealthy on boutique's website
        search_page.goto(website_url,timeout=30000)
        search_page.wait_for_load_state("domcontentloaded")  # Wait for the page to fully load
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
                search_page.wait_for_load_state("domcontentloaded")  # Wait for page load
                email_found = extract_email_from_rendered_text(search_page)
                if email_found:
                    print(f"Email found on {full_url}: {email_found}")
                    return email_found
            except Exception as e:
                print(f"Failed to load {full_url}: {e}")
        
        # Step 3: If no email found, perform a Google search as a fallback
        print(f"No email found on {website_url}. Performing Google search with site-specific query.")
        proxy_page = proxy_context.new_page() 
        email_found = perform_site_specific_google_search(proxy_page, website_url)
        proxy_page.close()
        return email_found

    finally:
        search_page.close()  # Ensure the tab is closed after search

def is_valid_url(url: str) -> bool:
    """Checks if the URL has a valid domain format."""
    url_pattern = r"^(http:\/\/www\.|https:\/\/www\.|http:\/\/|https:\/\/)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"
    return re.match(url_pattern, url) is not None

def scroll_to_load_more(page, required_items, max_scrolls=10):
    """
    Scroll the Google Maps results panel to load more listings.
    Stops scrolling when the required number of items is reached or max scrolls are exhausted.
    """
    try:
        # Locate the results panel using XPath
        results_panel_xpath = '//div[contains(@aria-label, "Results for")]'

        # Evaluate XPath and locate the results panel
        results_panel = page.evaluate('''
            (xpath) => {
                const panel = document.evaluate(
                    xpath,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                ).singleNodeValue;
                return panel ? panel : null;
            }
        ''', results_panel_xpath)

        if not results_panel:
            print("Results panel not found.")
            return

        previous_count = 0
        scroll_count = 0

        while scroll_count < max_scrolls:
            # Count the current number of listings
            current_count = len(page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all())
            print(f"Scrolling... Current count: {current_count}")

            # Stop if the required number of items is reached
            if current_count >= required_items:
                print(f"Required items ({required_items}) reached after {scroll_count} scrolls.")
                break

            # Stop if no new results are loaded
            if current_count == previous_count:
                print(f"No new results loaded after scroll {scroll_count}. Retrying 1 more time...")
                page.wait_for_timeout(20000)  # Wait a bit longer and retry
                current_count = len(page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all())
                if current_count == previous_count:  # Double-check after retry
                    print(f"Stopping scroll - no additional results after {scroll_count} scrolls.")
                    break

            # Update the previous count
            previous_count = current_count

            # Perform JavaScript scrolling
            scrolled = page.evaluate('''
                (xpath) => {
                    const panel = document.evaluate(
                        xpath,
                        document,
                        null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE,
                        null
                    ).singleNodeValue;
                    if (panel) {
                        panel.scrollTop += 2000;
                        return true;
                    } else {
                        return false;
                    }
                }
            ''', results_panel_xpath)

            if not scrolled:
                print("Unable to scroll - panel not found or undefined.")
                break

            # Wait for results to load
            page.wait_for_timeout(3000)  # Adjust wait time as needed
            scroll_count += 1

        # Final check: Ensure enough items are loaded
        final_count = len(page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all())
        if final_count < required_items:
            print(f"Warning: Only {final_count}/{required_items} listings loaded after {scroll_count} scrolls.")
        else:
            print(f"Final listing count matches or exceeds the required items: {final_count}.")

    except Exception as e:
        print(f"Error during scrolling: {e}")


def sanitize_filename(filename: str) -> str:
    return "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-')).strip()




# --------------------------------
# Main Scraping Start
# --------------------------------
def scrape_google_maps(proxy_server, proxy_username, proxy_password, user_agent, delay, total, suburb, state):
    """
    Scrapes Google Maps for businesses based on suburb and state.
    Constructs a search query as 'boutiques in {suburb}, {state}'.
    """
    # Validate proxy and user_agent inputs
    if not (proxy_server.startswith("http://") and not proxy_server.startswith("https://")):
        raise ValueError(f"Invalid proxy format: {proxy_server}")
    if not user_agent:
        raise ValueError("User agent cannot be empty.")
    
    search_query = f"boutiques in +{suburb}, {state}"  # Constructing the search query
    print(f"Search query: {search_query}")
    output_file_suffix = f"{suburb}_{state}".replace(" ", "_")

    # --------------------------------
    # Playwright Browser Setup
    # --------------------------------
    #debug: various prints to console
    print(f"the proxy url is : {proxy_server}")
    print(f"User-Agent string: {user_agent}")
    #below are useless. as you need to supply username and password.
    #ip = requests.get("https://api64.ipify.org?format=json", proxies={"http": proxy_server}).json()["ip"]
    #print(f"IPppp address visible to Google Maps: {ip}")

    
    #actual start of playwright
    with sync_playwright() as p:
        #creating proxy_browser context
        proxy_browser = p.chromium.launch(
            headless=False, 
            proxy={
                "server": proxy_server,
                "username": proxy_username,
                "password": proxy_password 
            },
            #args=["--disable-external-protocols", "--disable-popup-blocking","--disable-blink-features=AutomationControlled", "--no-first-run","--disable-infobars"]
            args=["--disable-blink-features=AutomationControlled"]
        )
       
        # Non-proxy browser for boutique websites
        local_browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
     

        try:
            viewport_width = random.randint(1024, 1920)
            viewport_height = random.randint(768, 1080)
            print(f"Using viewport size: {viewport_width}x{viewport_height}")
            proxy_context = proxy_browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},  # Randomized size
                user_agent=user_agent
            )  # Create a context for multiple tabs
            page = proxy_context.new_page()  # Original Google Maps page

            # Check IP address visible to the browser
            page.goto("https://api64.ipify.org?format=json", timeout=10000)
            ip = page.inner_text("body")
            print(f"IP address visible to websites: {ip}")


            page.goto("https://www.google.com/maps", timeout=60000)
            #page.goto("https://arh.antoinevastel.com/bots/areyouheadless", timeout=60000)
            page.wait_for_timeout(delay * 1000)
            

            # Loop over each search term

            page.locator('//input[@id="searchboxinput"]').fill(search_query)
            page.wait_for_timeout(3000)
            page.keyboard.press("Enter")
            page.wait_for_selector('//div[contains(@aria-label, "Results for")]', timeout=30000) #wait at most 15k;can be quicker



            scroll_to_load_more(page, total)  # Ensure all listings are loaded
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
                            # Create a local IP context for boutique website interactions
                            local_context = local_browser.new_context(
                                viewport={"width": viewport_width, "height": viewport_height},
                                user_agent=user_agent
                            )
                            #test print myip to make sure not use proxy here
                            local_page = local_context.new_page()
                            local_page.goto("https://api64.ipify.org?format=json", timeout=10000)
                            local_ip = local_page.inner_text("body")
                            print(f"Local browser IP address: {local_ip}")
                            #pass non-proxy context to below function to crawl non-google-site.
                            business.email = search_email_on_website(local_context, business.website,proxy_context)  # pass both context
                            local_context.close()  # Close the context after use
                        else:
                            print(f"Invalid URL skipped: {business.website}")
                    
                except Exception as e:
                    print(f"Error extracting business details: {e}")
                finally:
                    business_list.business_list.append(business)                    

            # --------------------------------
            # Save Results
            # --------------------------------
            business_list.save_to_excel(sanitize_filename(output_file_suffix))
            business_list.save_to_csv(sanitize_filename(output_file_suffix))
        finally:
            proxy_browser.close()
            local_browser.close()


