import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os
from download_pdfs import download_pdf, process_article_links
import logging
import schedule
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_articles.log'),
        logging.StreamHandler()
    ]
)

def search_arxiv():
    """Search arXiv for top AI papers"""
    base_url = "http://export.arxiv.org/api/query"
    query = "(cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:eess.AS OR cat:stat.ML)"
    params = {
        "search_query": query,
        "sortBy": "lastUpdatedDate",
        "sortOrder": "descending",
        "start": 0,
        "max_results": 50  # Get more than needed to filter by citations
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        # Parse with BeautifulSoup using 'xml' parser
        soup = BeautifulSoup(response.content, "xml")
        
        articles = []
        for entry in soup.find_all("entry"):
            arxiv_id = entry.id.text.split("abs/")[-1]
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            title = entry.title.text.strip()
            published = entry.published.text.strip()
            
            article = {
                'title': title,
                'url': pdf_url,
                'published': published,
                'citations': 0  # We'll update this with semantic scholar data
            }
            articles.append(article)
            logging.info(f"Found article: {title}")
        
        logging.info(f"Found {len(articles)} articles from arXiv")
        return articles
    except Exception as e:
        logging.error(f"Error searching arXiv: {str(e)}")
        return []

def get_semantic_scholar_data(title):
    """Get citation count from Semantic Scholar"""
    base_url = 'https://api.semanticscholar.org/graph/v1/paper/search'
    params = {
        'query': title,
        'fields': 'citationCount,title',
        'limit': 1
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; AIResearchAssistant/1.0; +http://example.com)'
    }
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('data') and len(data['data']) > 0:
            return data['data'][0].get('citationCount', 0)
        return 0
    except Exception as e:
        logging.error(f"Error getting citation data: {str(e)}")
        return 0

def update_articles():
    """Main function to update the article database"""
    logging.info("Starting article update process...")
    
    # Create directories if they don't exist
    pdf_dir = "pdfDatabase"
    os.makedirs(pdf_dir, exist_ok=True)
    
    # Get recent papers from arXiv
    articles = search_arxiv()
    
    # Update citation counts
    for article in articles:
        article['citations'] = get_semantic_scholar_data(article['title'])
    
    # Sort by citations and get top 20
    top_articles = sorted(articles, key=lambda x: x['citations'], reverse=True)[:20]
    
    # Download PDFs
    article_urls = [article['url'] for article in top_articles]
    process_article_links(article_urls)
    
    # Save metadata
    metadata = {
        'last_updated': datetime.now().isoformat(),
        'articles': top_articles
    }
    
    with open(os.path.join(pdf_dir, 'metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logging.info(f"Updated {len(top_articles)} articles successfully")

# def schedule_updates():
#     """Schedule regular updates"""
#     # Run updates daily at midnight
#     schedule.every().day.at("00:00").do(update_articles)
    
#     while True:
#         schedule.run_pending()
#         time.sleep(3600)  # Check every hour

if __name__ == "__main__":
    # Run initial update
    update_articles()
    # Start scheduling
    # schedule_updates()
