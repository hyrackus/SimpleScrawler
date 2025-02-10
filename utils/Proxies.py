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