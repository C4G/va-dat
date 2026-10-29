import requests
from datetime import datetime
from typing import Optional

def download_html(url:str, filename:Optional[str]):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            domain = url.replace('https://', '').replace('http://', '').split('/')[0]
            filename = f"{domain}_{timestamp}.html"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"HTML saved to {filename}")
        return filename
        
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__=='__main__':
    download_html("https://visionaid.org/")