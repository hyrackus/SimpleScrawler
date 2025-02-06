import requests
import re
import time
import random
import pandas as pd
from bs4 import BeautifulSoup
from googletrans import Translator
from fake_useragent import UserAgent
from tqdm import tqdm

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
        
        return proxies
    except Exception as e:
        print(f"Error fetching proxies: {e}")
        return []

PROXIES = get_proxies()
print(f"Using {len(PROXIES)} proxies")

ua = UserAgent()
translator = Translator()
TRANSLATION_CACHE = {}

def get_proxy():
    return {"http": random.choice(PROXIES), "https": random.choice(PROXIES)} if PROXIES else None

def get_country_data():
    try:
        url = "http://api.geonames.org/countryInfoJSON?username=your_username"
        response = requests.get(url, timeout=10).json()
        return {country['countryCode']: country['countryName'] for country in response.get('geonames', [])}
    except Exception as e:
        print(f"Error fetching country data: {e}")
        return {}

def get_country_languages(country_code):
    try:
        url = f"https://restcountries.com/v3.1/alpha/{country_code}"
        response = requests.get(url, timeout=10).json()
        return list(response[0]["languages"].values()) if isinstance(response, list) and "languages" in response[0] else []
    except Exception as e:
        print(f"Error fetching languages for {country_code}: {e}")
        return []

def translate_university(country_code):
    if country_code in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[country_code]
    
    languages = get_country_languages(country_code)
    if not languages:
        return "University"
    
    try:
        translation = translator.translate("University", dest=languages[0]).text
        TRANSLATION_CACHE[country_code] = translation
        return translation
    except Exception as e:
        print(f"Translation error for {country_code}: {e}")
        return "University"

def search_universities(query):
    search_engines = [
        f"https://www.google.com/search?q={query}",
        f"https://www.bing.com/search?q={query}"
    ]
    results = []
    
    for search_url in search_engines:
        try:
            headers = {"User-Agent": ua.random}
            proxy = get_proxy()
            response = requests.get(search_url, headers=headers, proxies=proxy, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all("a", href=True):
                url = link["href"]
                if "http" in url and not any(bad in url for bad in ["google", "bing", "youtube", "facebook", "wikipedia"]):
                    results.append(url)
            
            time.sleep(random.uniform(3, 7))
        except Exception as e:
            print(f"Error fetching {search_url}: {e}")
    
    return list(set(results))

def main():
    country_data = get_country_data()
    data = []
    
    for country_code, country_name in tqdm(country_data.items(), desc="Processing countries"):
        translation = translate_university(country_code)
        search_query = f"{translation} {country_name}"
        university_links = search_universities(search_query)
        
        for link in university_links:
            data.append([country_name, country_code, translation, link])
    
    df = pd.DataFrame(data, columns=["Country", "Country Code", "Translation", "University Website"])
    df.drop_duplicates(subset=["University Website"], inplace=True)
    df.to_csv("universities.csv", index=False)
    
    print("✅ CSV file created successfully!")

if __name__ == "__main__":
    main()
