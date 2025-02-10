import random
import json
import requests
from escrape import scrape_google_maps
import time

# Load ProxyScrape credentials from config.json
def load_credentials(file_path="config.json"):
    """
    Load ProxyScrape credentials from a JSON file.
    The file must contain "username", "password", and "proxy" keys.
    """
    try:
        with open(file_path, "r") as f:
            credentials = json.load(f)
            if "username" not in credentials or "password" not in credentials or "proxy" not in credentials:
                raise ValueError("Invalid config.json: Missing required keys (username, password, proxy).")
            return credentials
    except Exception as e:
        print(f"Error loading credentials: {e}")
        exit(1)

# Load credentials
credentials = load_credentials()

# Construct proxy details
username = credentials["username"]
password = credentials["password"]
proxy = credentials["proxy"]
proxy_auth = f"{username}:{password}@{proxy}"
proxies = {
    "http": f"http://{proxy_auth}"
}

# Test the proxy
def test_proxy():
    """
    Test if the proxy is working by sending a request to ip-api.com.
    """
    test_url = "http://ip-api.com/json"
    try:
        r = requests.get(test_url, proxies=proxies, timeout=10)
        r.raise_for_status()
        print("Proxy verification successful.")
    except Exception as e:
        print(f"Error verifying proxy: {e}")
        exit(1)

test_proxy()  # Verify proxy before proceeding

# Load user agents from file
with open("user_agents_desktop.txt", "r") as f:
    user_agents = [line.strip() for line in f.readlines() if line.strip()]

# Load suburbs and states from file
with open("suburbs.txt", "r") as f:
    suburbs = [line.strip() for line in f.readlines() if line.strip()]

# Check if user agents and suburbs are loaded
if not user_agents:
    print("No valid user agents found. Exiting.")
    exit(1)

if not suburbs:
    print("No valid suburbs found. Exiting.")
    exit(1)

# Loop through suburbs
for suburb in suburbs:

    start_time = time.time() #start the timer for complete a suburb
    user_agent = random.choice(user_agents)  # Random user agent
    delay = random.randint(2, 5)  # Example random delay
    total = 40  # Number of businesses to scrape (default for now)

    # Split suburb into state and suburb names
    if "," in suburb:
        parts = [x.strip() for x in suburb.split(",")]
        if len(parts) == 3:
            suburb_name, state, _ = parts  # Ignore postcode
            print(f"The suburb print: {suburb_name}, {state}")

            # Call scrape_google_maps function
            #scrape_google_maps(proxies["http"], user_agent, delay, total, suburb_name, state)
            scrape_google_maps(
                proxy_server=f"http://{proxy}", 
                proxy_username=username, 
                proxy_password=password, 
                user_agent=user_agent, 
                delay=delay, 
                total = total, 
                suburb=suburb_name, 
                state=state
                )
        else:
            print(f"Invalid suburb format: {suburb}. Skipping.")
            continue
    else:
        print(f"Invalid suburb format: {suburb}. Skipping.")
    # Record the end time
    end_time = time.time()

    # Calculate and print the time taken
    elapsed_time = end_time - start_time
    print(f"Completed processing for suburb: {suburb} in {elapsed_time:.2f} seconds.")