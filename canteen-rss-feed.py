import requests
from bs4 import BeautifulSoup
import datetime
import pytz  # Import pytz for timezone support
from feedgen.feed import FeedGenerator

# URL of the canteen menu
MENU_URL = "https://hubnordic.madkastel.dk/"
RSS_FILE = "feed.xml"

def scrape_menu():
    """Scrapes the daily menu from the website."""
    response = requests.get(MENU_URL)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find the menu section (Adjust this if needed)
    menu_section = soup.find("div", class_="content-box")  # Adjust class based on actual HTML structure
    if not menu_section:
        return ["Menu not found."]

    # Extract menu items
    menu_items = [item.get_text(strip=True) for item in menu_section.find_all("p") if item.get_text(strip=True)]
    
    return menu_items

def generate_rss(menu_items):
    """Generates and saves an RSS feed from the menu items."""
    fg = FeedGenerator()
    fg.title("Hub Nordic Canteen Menu")
    fg.link(href=MENU_URL)
    fg.description("Daily updated canteen menu")
    fg.language("en")

    today = datetime.date.today().strftime("%A, %d %B %Y")

    entry = fg.add_entry()
    entry.title(f"Canteen Menu for {today}")
    entry.link(href=MENU_URL)
    entry.description("<br>".join(menu_items))
    
    # Use timezone-aware UTC datetime
    utc_time = datetime.datetime.now(pytz.utc)
    entry.pubDate(utc_time)

    fg.rss_file(RSS_FILE)  # Save as RSS XML file
    print("✅ RSS feed updated!")

if __name__ == "__main__":
    menu_items = scrape_menu()
    generate_rss(menu_items)

