import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin
import time
from tqdm import tqdm
import logging
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_download.log'),
        logging.StreamHandler()
    ]
)

# Configure retry strategy
def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=5,  # maximum number of retries
        backoff_factor=1,  # wait 1, 2, 4, 8, 16 seconds between retries
        status_forcelist=[429, 500, 502, 503, 504],  # status codes to retry on
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Global session
session = create_session()

def get_pdf_url(article_url):
    """
    Visit the article page and find the PDF download link.
    """
    try:
        # Use session with retry logic
        response = session.get(article_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try different patterns to find PDF links
        pdf_patterns = [
            # Look for links containing 'pdf' in href
            lambda s: s.find_all('a', href=lambda x: x and 'pdf' in x.lower()),
            # Look for links containing 'download' in href
            lambda s: s.find_all('a', href=lambda x: x and 'download' in x.lower()),
            # Look for links containing 'report' in href
            lambda s: s.find_all('a', href=lambda x: x and 'report' in x.lower()),
            # Look for links with specific text patterns
            lambda s: s.find_all('a', string=lambda x: x and any(term in x.lower() for term in ['report', 'download', 'pdf'])),
        ]
        
        for pattern in pdf_patterns:
            links = pattern(soup)
            if links:
                for link in links:
                    href = link.get('href')
                    if href:
                        full_url = urljoin(article_url, href)
                        logging.info(f"Found potential PDF link: {full_url}")
                        # Try to verify if it's a PDF
                        try:
                            head = requests.head(full_url, allow_redirects=True)
                            content_type = head.headers.get('content-type', '')
                            if 'pdf' in content_type.lower():
                                return full_url
                        except Exception as e:
                            logging.warning(f"Error checking PDF link {full_url}: {str(e)}")
                            continue
        
        logging.warning(f"No PDF link found in {article_url}")
        return None
    except Exception as e:
        logging.error(f"Error accessing article page {article_url}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Error accessing article page {article_url}: {str(e)}")
        return None

def get_pdf_filename(pdf_url, response):
    """
    Extract filename from URL or Content-Disposition header.
    Ensures the filename ends with .pdf
    """
    filename = pdf_url.split('/')[-1]
    if 'Content-Disposition' in response.headers:
        content_disp = response.headers['Content-Disposition']
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[-1].strip('"\'')
    
    # Clean up filename: remove query parameters and ensure .pdf extension
    filename = filename.split('?')[0]  # Remove query parameters
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'
    
    return filename

def download_pdf(pdf_url, output_dir):
    """
    Download a PDF file and save it to the output directory.
    Returns the path to the downloaded file.
    """
    try:
        # First make a HEAD request to get headers without downloading content
        head_response = session.head(pdf_url, allow_redirects=True)
        head_response.raise_for_status()
        
        # Get filename and create output path
        filename = get_pdf_filename(pdf_url, head_response)
        output_path = output_dir / filename
        
        # Check if file already exists and get its size
        if output_path.exists():
            existing_size = output_path.stat().st_size
            expected_size = int(head_response.headers.get('content-length', 0))
            
            # If sizes match, skip download
            if existing_size == expected_size:
                logging.info(f"Skipping {filename} - already exists with correct size")
                return output_path
            else:
                logging.info(f"Re-downloading {filename} - size mismatch (existing: {existing_size}, expected: {expected_size})")
        
        # Download the file with retry logic
        response = session.get(pdf_url, stream=True)
        response.raise_for_status()
        
        # Download with progress bar
        total_size = int(response.headers.get('content-length', 0))
        with open(output_path, 'wb') as f, tqdm(
            desc=filename,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as pbar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                pbar.update(size)
        
        # Add a small delay between downloads to avoid rate limiting
        time.sleep(0.5)
        
        logging.info(f"Successfully downloaded {filename}")
        return output_path
    except Exception as e:
        logging.error(f"Error downloading PDF from {pdf_url}: {str(e)}")
        return None

def process_article_links(article_links):
    """
    Process a list of article links and download their PDFs.
    """
    # Create output directory if it doesn't exist
    output_dir = Path('pdfs')
    output_dir.mkdir(exist_ok=True)
    
    downloaded_files = []
    
    for link in tqdm(article_links, desc="Processing articles"):
        logging.info(f"Processing article: {link}")
        
        # Find PDF URL
        pdf_url = get_pdf_url(link)
        if not pdf_url:
            continue
        
        # Add delay to be nice to the server
        time.sleep(1)
        
        # Download PDF
        pdf_path = download_pdf(pdf_url, output_dir)
        if pdf_path:
            downloaded_files.append(pdf_path)
    
    return downloaded_files

def main():
    # Example usage
    base_url = "https://www.mhrc.ca"
    article_links = [
        f"{base_url}/national-polling",
        f"{base_url}/key-facts-on-mental-health",
        f"{base_url}/research-briefs"
    ]
    
    # Add delay between requests to avoid rate limiting
    time.sleep(1)
    
    if not article_links:
        logging.warning("No article links provided. Please add links to the article_links list.")
        return
    
    # First, try to find additional links on the main pages
    all_links = set()
    for url in article_links:
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links that might lead to PDFs or report pages
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href:
                    # Check if the link might be relevant
                    if any(term in href.lower() or (link.text and term in link.text.lower())
                           for term in ['poll', 'report', 'research', 'study', 'findings']):
                        full_url = urljoin(url, href)
                        if base_url in full_url:  # Only include links from the same domain
                            all_links.add(full_url)
                            logging.info(f"Found potential report link: {full_url}")
        except Exception as e:
            logging.error(f"Error processing page {url}: {str(e)}")
    
    # Add the original links to the set
    all_links.update(article_links)
    
    # Process all discovered links
    downloaded_files = process_article_links(list(all_links))
    
    logging.info(f"Downloaded {len(downloaded_files)} PDFs:")
    for file in downloaded_files:
        logging.info(f"- {file}")

if __name__ == "__main__":
    main()
