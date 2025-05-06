import requests
from bs4 import BeautifulSoup

def get_latest_arxiv_pdfs():
    base_url = "http://export.arxiv.org/api/query"
    query = "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:eess.AS OR cat:stat.ML)"
    params = {
        "search_query": query,
        "sortBy": "lastUpdatedDate",
        "sortOrder": "descending",
        "start": 0,
        "max_results": 10
    }

    response = requests.get(base_url, params=params)
    soup = BeautifulSoup(response.content, "xml")

    articles = []
    for entry in soup.find_all("entry"):
        arxiv_id = entry.id.text.split("abs/")[-1]
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        title = entry.title.text.strip()
        articles.append((title, pdf_url))

    return articles

# Print the results
for title, pdf in get_latest_arxiv_pdfs():
    print(f"{title}\n{pdf}\n")
