import sys
import os
import requests
import time
import tracemalloc
import random
from scholarly import scholarly, ProxyGenerator
from scholarly._proxy_generator import MaxTriesExceededException
from bs4 import BeautifulSoup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.Database_Calls import insert_paper, search_papers

def measure_performance(func, *args):
    start_time = time.time()
    tracemalloc.start()
    result = func(*args)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    end_time = time.time()
    
    print(f"Function {func.__name__} took {end_time - start_time:.4f} seconds to execute.")
    print(f"Current memory usage: {current / 10**6:.4f} MB; Peak memory usage: {peak / 10**6:.4f} MB")
    return result

def fetch_google_scholar(query):
    pg = ProxyGenerator()
    success = pg.FreeProxies()  # Uses free proxies
    scholarly.use_proxy(pg)
    
    formatted_query = f'"{query}"'
    try:
        search_query = scholarly.search_pubs(formatted_query)
        count = 0
        for result in search_query:
            paper = scholarly.fill(result)
            insert_paper(
                paper.get("bib", {}).get("title", "Unknown"),
                ", ".join(paper.get("bib", {}).get("author", ["Unknown"])),
                paper.get("bib", {}).get("pub_year", None),
                "Google Scholar",
                paper.get("pub_url", ""),
                paper.get("bib", {}).get("abstract", ""),
                query,
                paper.get("num_citations", 0)
            )
            count += 1
            time.sleep(random.uniform(2, 5))
        print(f"Google Scholar fetched {count} results.")
    except MaxTriesExceededException:
        print("Google Scholar blocked requests. Consider using a proxy.")

def fetch_crossref(query):
    base_url = "https://api.crossref.org/works"
    params = {"query": query, "rows": 20}
    response = requests.get(base_url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        count = 0
        for item in data["message"]["items"]:
            title = item.get("title", ["Unknown"])[0]
            authors = ", ".join([author.get("given", "Unknown") + " " + author.get("family", "Unknown") for author in item.get("author", [])])
            year = item.get("published-print", {}).get("date-parts", [[None]])[0][0]
            link = item.get("URL", "")
            insert_paper(title, authors, year, "Crossref", link, "", query, 0)
            count += 1
        print(f"Crossref fetched {count} results.")

def fetch_pubmed(query):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 100  # Increased to fetch more results
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        print(f"PubMed fetched {len(ids)} results.")
        for pubmed_id in ids:
            fetch_pubmed_details(pubmed_id)

def fetch_pubmed_details(pubmed_id):
    details_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pubmed_id, "retmode": "json"}
    response = requests.get(details_url, params=params)
    if response.status_code == 200:
        summary = response.json().get("result", {}).get(pubmed_id, {})
        insert_paper(
            summary.get("title", "Unknown"),
            ", ".join([author.get("name", "Unknown") for author in summary.get("authors", [])]),
            summary.get("pubdate", "").split(" ")[0],
            "PubMed",
            f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}",
            summary.get("source", ""),
            summary.get("title", ""),
            0
        )

def fetch_paperity(query):
    base_url = "https://paperity.org/search/"
    params = {"q": query, "f": "paper"}
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        papers = soup.find_all("article", class_="item")
        count = 0
        for paper in papers:
            title_element = paper.find("h2")
            link_element = paper.find("a")
            title = title_element.text.strip() if title_element else "Unknown"
            link = link_element["href"] if link_element else ""
            insert_paper(
                title,
                "Unknown",
                None,
                "Paperity",
                link,
                "",
                query,
                0
            )
            count += 1
        print(f"Paperity fetched {count} results.")

if __name__ == "__main__":
    query = "plant adaptation climate genomic offset"
    measure_performance(fetch_google_scholar, query)
    measure_performance(fetch_crossref, query)
    measure_performance(fetch_pubmed, query)
    measure_performance(fetch_paperity, query)
    
    print("Papers matching 'genomics':", search_papers("genomics"))
