import sqlite3
import pandas as pd
import tqdm
import openpyxl

def create_database():
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    
    # Table for scientific papers & reviews
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            authors TEXT,
            year INTEGER,
            source TEXT,
            link TEXT,
            abstract TEXT,
            keywords TEXT,
            citations INTEGER DEFAULT 0
        )
    ''')
    
    # Table for research projects from universities/companies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            institution TEXT,
            country TEXT,
            start_year INTEGER,
            end_year INTEGER,
            researchers TEXT,
            link TEXT,
            abstract TEXT,
            keywords TEXT
        )
    ''')
    
    # Indexes for faster searches
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_keywords ON papers(keywords)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_keywords ON projects(keywords)")
    
    conn.commit()
    conn.close()
    print("Database and tables created successfully!")

def insert_paper(title, authors, year, source, link, abstract, keywords, citations=0):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO papers (title, authors, year, source, link, abstract, keywords, citations)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, authors, year, source, link, abstract, keywords, citations))
    conn.commit()
    conn.close()

def insert_project(title, institution, country, start_year, end_year, researchers, link, abstract, keywords):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (title, institution, country, start_year, end_year, researchers, link, abstract, keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, institution, country, start_year, end_year, researchers, link, abstract, keywords))
    conn.commit()
    conn.close()

def search_papers(keyword):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM papers WHERE title LIKE ? OR authors LIKE ? OR abstract LIKE ? OR keywords LIKE ?
    ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
    results = cursor.fetchall()
    conn.close()
    return results

def search_projects(keyword):
    conn = sqlite3.connect("research.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM projects WHERE title LIKE ? OR institution LIKE ? OR abstract LIKE ? OR keywords LIKE ?
    ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
    results = cursor.fetchall()
    conn.close()
    return results

def export_to_excel(db_path="research.db", output_file="research_results.xlsx"):
    conn = sqlite3.connect(db_path)
    papers_df = pd.read_sql_query("SELECT * FROM papers", conn)
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    conn.close()
    
    with pd.ExcelWriter(output_file) as writer:
        papers_df.to_excel(writer, sheet_name="Papers", index=False)
        projects_df.to_excel(writer, sheet_name="Projects", index=False)



def remove_duplicates_from_db():
    conn = sqlite3.connect("research.db")  # Change to PostgreSQL connection if needed
    cursor = conn.cursor()
    
    # Deduplication logic: Keep the first occurrence of (title, authors, source)
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

if __name__ == "__main__":
    create_database()

    # Example search
    #print("Papers matching 'genomics':", search_papers("genomics"))
    #print("Projects matching 'climate':", search_projects("climate"))