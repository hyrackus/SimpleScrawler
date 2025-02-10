import sys
import os
import requests
import time
import tracemalloc
import random
import urllib.parse
import xml.etree.ElementTree as ET
from scholarly import scholarly, ProxyGenerator
from scholarly._proxy_generator import MaxTriesExceededException
from bs4 import BeautifulSoup
from tqdm import tqdm
from fake_useragent import UserAgent
import sqlite3

# Append parent directory if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ---------------- Database Functions ----------------

def insert_paper(title, authors, year, source, link, abstract, keywords, citations=0):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO papers (title, authors, year, source, link, abstract, keywords, citations)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, authors, year, source, link, abstract, keywords, citations))
    conn.commit()
    conn.close()

def remove_duplicates_from_db():
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    query = """
    DELETE FROM papers
    WHERE rowid NOT IN (
        SELECT MIN(rowid)
        FROM papers
        GROUP BY title, authors, source
    );
    """
    cursor.execute(query)
    conn.commit()
    conn.close()
    print("Duplicates removed successfully!")

def search_papers(keyword):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM papers WHERE title LIKE ?", ('%' + keyword + '%',))
    results = cursor.fetchall()
    conn.close()
    return results

# ---------------- Helper Functions for Query Handling ----------------

def ensure_query_string(query):
    """
    If query is a list, join its elements with " OR ".
    Otherwise, return it unchanged.
    """
    if isinstance(query, list):
        return " OR ".join(query)
    return query

def build_hal_query_from_phrases(phrases):
    """
    Given a list of phrases (e.g. ["Genomic offset", "Plant adaptation", "Climate change"]),
    build a Solr query that searches for these phrases (exact match) in either the title_s or abstract_s field.
    
    The resulting query will look like:
      (title_s:("Genomic offset") OR title_s:("Plant adaptation") OR title_s:("Climate change") OR
       abstract_s:("Genomic offset") OR abstract_s:("Plant adaptation") OR abstract_s:("Climate change"))
    """
    title_queries = [f'title_s:("{phrase}")' for phrase in phrases]
    abstract_queries = [f'abstract_s:("{phrase}")' for phrase in phrases]
    combined = " OR ".join(title_queries + abstract_queries)
    return f"({combined})"

def build_theses_fr_query_phrases(phrases):
    """
    Given a list of phrases, build a query for Thèses.fr (REST API) that searches in the sujetsLibelle field.
    Each phrase is enclosed in quotes and appended with a wildcard.
    For example, if phrases is:
         ["Genomic offset", "Plant adaptation", "Climate change"]
    the returned query will be:
         sujetsLibelle:("Genomic offset"* OR "Plant adaptation"* OR "Climate change"*)
    """
    terms = [f'"{phrase}"*' for phrase in phrases]
    return f'sujetsLibelle:({" OR ".join(terms)})'

def format_author(author: dict) -> str:
    """
    Converts an author dictionary to a string.
    If the dictionary contains a 'nomComplet' field, that is used.
    Otherwise, it attempts to join the 'prenom' and 'nom' fields.
    """
    if "nomComplet" in author and author["nomComplet"]:
        return author["nomComplet"]
    else:
        parts = []
        if author.get("prenom"):
            parts.append(author.get("prenom").strip())
        if author.get("nom"):
            parts.append(author.get("nom").strip())
        return " ".join(parts) if parts else "Unknown Author"

# ---------------- Performance Measurement ----------------

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

# ---------------- API/Scraper Functions ----------------

def fetch_google_scholar(query):
    query_str = ensure_query_string(query)
    pg = ProxyGenerator()
    for _ in range(3):
        proxy = None  # Replace with get_proxy() if available
        if proxy:
            pg.SingleProxy(http=proxy["http"], https=proxy["https"])
            scholarly.use_proxy(pg)
        else:
            print("⚠️ No proxies available. Skipping Google Scholar.")
            return
        try:
            search_query = scholarly.search_pubs(f'"{query_str}"')
            count = 0
            for result in search_query:
                paper = scholarly.fill(result)
                insert_paper(
                    title=paper.get("bib", {}).get("title", "Unknown"),
                    authors=", ".join(paper.get("bib", {}).get("author", ["Unknown"])),
                    year=paper.get("bib", {}).get("pub_year", None),
                    source="Google Scholar",
                    link=paper.get("pub_url", ""),
                    abstract=paper.get("bib", {}).get("abstract", ""),
                    keywords=query_str,
                    citations=paper.get("num_citations", 0)
                )
                count += 1
                time.sleep(random.uniform(2, 5))
            print(f"✅ Google Scholar fetched {count} results.")
            return
        except MaxTriesExceededException:
            print("❌ Google Scholar blocked request. Retrying...")
            continue
    print("❌ Google Scholar failed after maximum retries.")

def fetch_crossref(query):
    query_str = ensure_query_string(query)
    base_url = "https://api.crossref.org/works"
    params = {"query": query_str, "rows": 20}
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        items = data["message"]["items"]
        print(f"Crossref found {len(items)} results.")
        for item in items:
            title = item.get("title", ["Unknown"])[0]
            authors = ", ".join([f'{author.get("given", "Unknown")} {author.get("family", "Unknown")}' for author in item.get("author", [])])
            year = item.get("published-print", {}).get("date-parts", [[None]])[0][0]
            link = item.get("URL", "")
            insert_paper(
                title=title,
                authors=authors,
                year=year,
                source="Crossref",
                link=link,
                abstract="",
                keywords=query_str,
                citations=0
            )
    else:
        print(f"Crossref request failed with status code {response.status_code}")

def fetch_pubmed(query):
    query_str = ensure_query_string(query)
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query_str,
        "retmode": "json",
        "retmax": 100
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        print(f"PubMed found {len(ids)} results.")
        for pubmed_id in ids:
            fetch_pubmed_details(pubmed_id)
    else:
        print(f"PubMed request failed with status code {response.status_code}")

def fetch_pubmed_details(pubmed_id):
    details_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": pubmed_id, "retmode": "json"}
    response = requests.get(details_url, params=params)
    if response.status_code == 200:
        summary = response.json().get("result", {}).get(pubmed_id, {})
        insert_paper(
            title=summary.get("title", "Unknown"),
            authors=", ".join([author.get("name", "Unknown") for author in summary.get("authors", [])]),
            year=summary.get("pubdate", "").split(" ")[0],
            source="PubMed",
            link=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}",
            abstract=summary.get("source", ""),
            keywords=str(pubmed_id),
            citations=0
        )

def fetch_paperity(query):
    query_str = ensure_query_string(query)
    base_url = "https://paperity.org/search/"
    formatted_query = query_str.replace(" ", "+")
    search_url = f"{base_url}?q=\"{formatted_query}\""
    for _ in range(3):
        proxy = None  # Replace with get_proxy() if available
        headers = {
            "User-Agent": UserAgent().random,
            "Referer": "https://paperity.org/",
        }
        try:
            response = requests.get(search_url, headers=headers, proxies=proxy, timeout=10)
            if response.status_code == 403:
                print(f"❌ Paperity blocked proxy {proxy}. Retrying...")
                continue
            if response.status_code != 200:
                print(f"⚠️ Paperity request failed with status code {response.status_code}.")
                return
            soup = BeautifulSoup(response.text, "html.parser")
            articles = soup.find_all("div", class_="row")
            if not articles:
                print("⚠️ No results found on Paperity. Possible structure change.")
                return
            print(f"✅ Paperity found {len(articles)} results.")
            for article in tqdm(articles, desc="Fetching Paperity papers"):
                title_element = article.find("h2", class_="paper-list-title")
                link_element = title_element.find("a") if title_element else None
                title = title_element.get_text(strip=True) if title_element else "Unknown"
                link = f"https://paperity.org{link_element['href']}" if link_element else ""
                author_element = article.find("p", class_="bib-authors")
                authors = author_element.get_text(strip=True) if author_element else "Unknown"
                date_element = article.find("p", class_="bib-date")
                publication_date = date_element.get_text(strip=True) if date_element else "Unknown"
                insert_paper(
                    title=title,
                    authors=authors,
                    year=publication_date,
                    source="Paperity",
                    link=link,
                    abstract="",
                    keywords=query_str,
                    citations=0
                )
            return
        except requests.exceptions.RequestException:
            print(f"❌ Paperity proxy {proxy} failed. Retrying...")
            continue
    print("❌ Paperity failed after maximum retries.")

def fetch_theses_fr(query, max_results=50):
    # For Thèses.fr, if query is not a list, convert it to a list.
    if not isinstance(query, list):
        query_phrases = [query]
    else:
        query_phrases = query
    q_param = build_theses_fr_query_phrases(query_phrases)
    base_url = "https://theses.fr/api/v1/theses/recherche/"
    params = {
        "q": q_param,
        "rows": max_results
    }
    headers = {
        "User-Agent": UserAgent().random,
        "Accept": "application/json",
        "Referer": "https://theses.fr/"
    }
    print(f"[Thèses.fr REST] Debug: Requesting REST API with params={params}")
    response = requests.get(base_url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(f"[Thèses.fr REST] Response keys: {list(data.keys())}")
    total_hits = data.get("totalHits", 0)
    print(f"[Thèses.fr REST] Total hits: {total_hits}")
    theses_list = data.get("theses", [])
    print(f"[Thèses.fr REST] Found {len(theses_list)} record(s).")
    for thesis in theses_list:
        title = thesis.get("titrePrincipal", "Unknown Title")
        authors_data = thesis.get("auteurs", [])
        authors = ", ".join(format_author(a) for a in authors_data) if authors_data else "Unknown Author"
        date_soutenance = thesis.get("dateSoutenance") or "Unknown Date"
        year = date_soutenance.split("-")[0] if date_soutenance != "Unknown Date" else "Unknown"
        nnt = thesis.get("nnt", "")
        link = f"https://www.theses.fr/{nnt}" if nnt else thesis.get("url", "")
        abstract = thesis.get("resumes", {}).get("fr", "")
        keywords = ensure_query_string(query) if not isinstance(query, list) else " OR ".join(query)
        insert_paper(
            title=title,
            authors=authors,
            year=year,
            source="Thèses.fr",
            link=link,
            abstract=abstract,
            keywords=keywords,
            citations=0
        )
    return len(theses_list)
def fetch_articles_hal(query_phrases, domain=None, max_records=50):
    """
    Searches HAL using the OAI-PMH interface at https://api.archives-ouvertes.fr/oai/hal/.
    
    - query_phrases: list of phrases (ignored by HAL OAI, since OAI-PMH doesn't allow ad-hoc keyword search).
      We'll harvest records, then optionally filter them locally if needed.
    - domain: optional set/domain name for OAI-PMH, e.g. 'hal:bio' for Life Sciences (Biology).
      You can see available sets at https://api.archives-ouvertes.fr/oai/hal/?verb=ListSets
    - max_records: maximum number of records to process.
    
    Returns:
      Number of processed records.
    """
    import xml.etree.ElementTree as ET
    from fake_useragent import UserAgent
    
    # Ensure we have a list of phrases
    if not isinstance(query_phrases, list):
        phrases = [query_phrases]
    else:
        phrases = query_phrases
    
    base_url = "https://api.archives-ouvertes.fr/oai/hal/"
    # Standard OAI-PMH parameters
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc"
    }
    if domain is not None:
        # OAI-PMH 'set=' parameter to filter by domain
        params["set"] = domain
    
    headers = {"User-Agent": UserAgent().random}
    print(f"[HAL OAI] Debug: Requesting OAI with params={params}")
    response = requests.get(base_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    
    # Parse the XML response
    root = ET.fromstring(response.content)
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"
    }
    records = root.findall(".//oai:record", ns)
    print(f"[HAL OAI] Found {len(records)} records in set={domain or 'ALL'}.")

    processed = 0
    for rec in records:
        if processed >= max_records:
            break
        metadata = rec.find("oai:metadata", ns)
        if metadata is None:
            continue
        
        dc = metadata.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
        if dc is None:
            dc = metadata.find("dc:dc", ns)
        if dc is None:
            continue
        
        # Extract some DC metadata
        title_el = dc.find("dc:title", ns)
        title = title_el.text if title_el is not None else "Unknown Title"
        
        creators = dc.findall("dc:creator", ns)
        authors_list = [creator.text for creator in creators if creator.text]
        authors = ", ".join(authors_list) if authors_list else "Unknown Author"
        
        date_el = dc.find("dc:date", ns)
        year = date_el.text if date_el is not None else "Unknown Date"
        
        # Typically we look for an identifier that starts with "https://"
        identifiers = dc.findall("dc:identifier", ns)
        link = ""
        for id_el in identifiers:
            if id_el.text and id_el.text.startswith("https://"):
                link = id_el.text
                break
        
        abstract_el = dc.find("dc:description", ns)
        abstract = abstract_el.text if abstract_el is not None else ""
        
        # Print debug info
        print("---- HAL OAI Entry ----")
        print(f"Title: {title}")
        print(f"Authors: {authors}")
        print(f"Date: {year}")
        print(f"Link: {link}")
        print("-----------------------")
        
        # Insert record into DB
        insert_paper(
            title=title,
            authors=authors,
            year=year,
            source=f"HAL OAI (Set={domain or 'All'})",
            link=link,
            abstract=abstract,
            keywords=" OR ".join(phrases),
            citations=0
        )
        processed += 1

    return processed

# ---------------- Main Execution ----------------

if __name__ == "__main__":
    # Use a list of phrases for your search.
    search_phrases = ["Genomic offset", "Plant adaptation", "Climate change"]
    # For functions expecting a single query string, join the list.
    query_string = ensure_query_string(search_phrases)
    
    # Uncomment whichever functions you want to run:
    # measure_performance(fetch_google_scholar, query_string)
    # measure_performance(fetch_crossref, query_string)
    # measure_performance(fetch_pubmed, query_string)
    # measure_performance(fetch_paperity, query_string)
    
    # For HAL and Thèses.fr, we call the functions that support a list of phrases.
    measure_performance(fetch_articles_hal, search_phrases)
    measure_performance(fetch_theses_fr, search_phrases)
    
    print("Removing duplicate entries from the database...")
    #remove_duplicates_from_db()
    
    print("Papers matching 'genomics':", search_papers("genomics"))
