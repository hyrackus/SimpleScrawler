import requests
import re
import time
import random
import json
import pandas as pd
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tqdm import tqdm
from requests.exceptions import ProxyError, ConnectTimeout

BAD_PROXIES_FILE = "bad_proxies.json"
OUTPUT_FILE = "universities.csv"
MAX_RETRIES = 5

# Load bad proxies from file
def load_bad_proxies():
    try:
        with open(BAD_PROXIES_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

# Save bad proxies to file
def save_bad_proxy(proxy):
    bad_proxies = load_bad_proxies()
    bad_proxies.add(proxy)
    with open(BAD_PROXIES_FILE, "w") as f:
        json.dump(list(bad_proxies), f, indent=4)

# Get proxies from free sources
def get_proxies():
    regex = r"[0-9]+(?:\.[0-9]+){3}:[0-9]+"
    try:
        c = requests.get("https://spys.me/proxy.txt", timeout=10)
        proxies = re.findall(regex, c.text)

        d = requests.get("https://free-proxy-list.net/", timeout=10)
        soup = BeautifulSoup(d.content, 'html.parser')

        for row in soup.select("#proxylisttable tbody tr"):
            cols = row.find_all("td")
            if cols[4].text.strip().lower() == "elite proxy":
                proxies.append(f"{cols[0].text.strip()}:{cols[1].text.strip()}")

        # Remove bad proxies
        bad_proxies = load_bad_proxies()
        proxies = [p for p in proxies if p not in bad_proxies]

        return proxies
    except Exception as e:
        print(f"Error fetching proxies: {e}")
        return []

PROXIES = get_proxies()
print(f"Using {len(PROXIES)} proxies after filtering bad ones")

ua = UserAgent()

# Get a random proxy
def get_proxy():
    if not PROXIES:
        return None
    proxy = random.choice(PROXIES)
    return {"http": f"http://{proxy}", "https": f"https://{proxy}"}

# Get all country codes
def get_country_data():
    try:
        url = "http://api.geonames.org/countryInfoJSON?username=miratesting"
        response = requests.get(url, timeout=10).json()
        return {country['countryCode']: country['countryName'] for country in response.get('geonames', [])}
    except Exception as e:
        print(f"Error fetching country data: {e}")
        return {}

# Scrape university names for a country
def get_universities(country_code, country_name):
    url = f"https://www.universityguru.com/{country_code}"
    universities = []
    headers = {"User-Agent": ua.random}

    for retries in range(MAX_RETRIES):
        proxy = get_proxy()
        try:
            print(f"Attempting to scrape {country_name} using proxy {proxy['http']}")
            time.sleep(random.uniform(3, 7))  # Random delay to avoid detection
            
            response = requests.get(url, headers=headers, proxies=proxy, timeout=10)
            if response.status_code == 403:
                raise ProxyError("403 Forbidden: Blocked by bot detection")

            soup = BeautifulSoup(response.text, 'html.parser')
            uni_list = soup.select("div.university-name a")

            for uni in uni_list:
                universities.append(uni.text.strip())

            print(f"✅ Scraped {len(universities)} universities from {country_name}")
            return universities

        except (ProxyError, ConnectTimeout) as e:
            proxy_address = proxy["http"].split("//")[1]  # Extract proxy address
            print(f"⚠️ Proxy failed: {proxy_address}. Retrying with a new proxy...")

            # Save bad proxy and remove it from the list
            save_bad_proxy(proxy_address)
            if proxy_address in PROXIES:
                PROXIES.remove(proxy_address)
            
            continue  # Retry with a new proxy

        except Exception as e:
            print(f"⚠️ Error scraping {country_name}: {e}")
            break  # Stop retrying for non-proxy-related issues

    return universities

# Main function
def scrape_all_universities():
    country_data = get_country_data()
    all_universities = []

    for country_code, country_name in tqdm(country_data.items(), desc="Scraping universities"):
        universities = get_universities(country_code.lower(), country_name)
        for uni in universities:
            all_universities.append({"Country": country_name, "University": uni})

    df = pd.DataFrame(all_universities)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(df)} universities to {OUTPUT_FILE}")

# Run the scraper
if __name__ == "__main__":
    scrape_all_universities()
