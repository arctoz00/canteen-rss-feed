import time
import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# URL of the canteen menu
MENU_URL = "https://hubnordic.madkastel.dk/"
RSS_FILE = "feed.xml"

def get_rendered_html():
    """
    Uses Selenium to load the webpage and return its fully rendered HTML.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    # Create the driver instance (adjust path if necessary)
    driver = webdriver.Chrome(options=chrome_options)
    
    driver.get(MENU_URL)
    
    try:
        # Wait for at least one hub container to load (adjust the CSS selector if needed)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    
    # Additional wait to ensure all JavaScript content has rendered
    time.sleep(2)
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parses the rendered HTML and extracts the weekly menus for all hubs.
    Returns a dictionary structured as:
      { hub_name: { day: [menu item strings] } }
    """
    html = get_rendered_html()
    soup = BeautifulSoup(html, "html.parser")
    
    # Find all containers that hold hub content.
    # (Based on the provided HTML snippets, each hub is inside a div with class "et_pb_text_inner")
    hub_divs = soup.find_all("div", class_="et_pb_text_inner")
    menus_by_hub = {}
    
    # List of valid Danish weekday names (in lowercase)
    valid_days = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']
    
    for div in hub_divs:
        # Each hub is expected to have an <h4> header with its name and time.
        header = div.find("h4")
        if not header:
            continue
        hub_header_text = header.get_text(separator=" ", strip=True)
        # For consistency, if this is HUB1, rename it as desired.
        if "hub1" in hub_header_text.lower():
            hub_name = "HUB1 – Kays Verdenskøkken"
        else:
            hub_name = hub_header_text  # For HUB2, HUB3, etc.
        
        # Initialize a dictionary for this hub’s weekly menu.
        hub_menus = {}
        current_day = None
        
        # Iterate over all <p> tags in the container in order.
        for p in div.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            # Check if this paragraph is a day heading.
            # Day headings might be like "MANDAG:" or "TIRSDAG:" etc.
            norm_text = text.replace(":", "").lower()
            if norm_text in valid_days:
                current_day = norm_text
                hub_menus[current_day] = []  # Start a new list for this day.
            else:
                # Only add text if a day heading has been seen.
                if current_day:
                    hub_menus[current_day].append(text)
        if hub_menus:
            menus_by_hub[hub_name] = hub_menus

    return menus_by_hub

def get_today_menus(menus_by_hub):
    """
    From the full weekly menus, extract today’s menu for each hub.
    Returns a list of strings, one per hub.
    """
    # Map English weekdays to Danish (lowercase)
    weekday_mapping = {
        "Monday": "mandag",
        "Tuesday": "tirsdag",
        "Wednesday": "onsdag",
        "Thursday": "torsdag",
        "Friday": "fredag",
        "Saturday": "lørdag",
        "Sunday": "søndag"
    }
    today_en = datetime.datetime.today().strftime("%A")
    today_da = weekday_mapping.get(today_en, "").lower()
    
    today_menus = []
    for hub, menu_dict in menus_by_hub.items():
        if today_da in menu_dict:
            # Combine all menu items for today (separated by " | " for clarity)
            menu_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {menu_text}")
        else:
            today_menus.append(f"{hub}: No menu found for {today_da.capitalize()}.")
    return today_menus

def generate_rss(menu_items):
    """
    Generates an RSS feed entry with today's menu and saves it to the RSS_FILE.
    """
    fg = FeedGenerator()
    fg.title("Hub Nordic Canteen Menu")
    fg.link(href=MENU_URL)
    fg.description("Daily updated canteen menu")
    fg.language("en")
    
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    entry = fg.add_entry()
    entry.title(f"Canteen Menu for {today_str}")
    entry.link(href=MENU_URL)
    entry.description("<br>".join(menu_items))
    
    # Use timezone-aware UTC datetime
    utc_time = datetime.datetime.now(pytz.utc)
    entry.pubDate(utc_time)
    
    fg.rss_file(RSS_FILE)
    print("✅ RSS feed updated!")

if __name__ == "__main__":
    # Scrape the weekly menus from all hubs
    menus_by_hub = scrape_weekly_menus()
    # For debugging: print the full weekly menus (optional)
    # import pprint
    # pprint.pprint(menus_by_hub)
    
    # Extract today's menu for each hub
    today_menus = get_today_menus(menus_by_hub)
    print("Today's menus:")
    for menu in today_menus:
        print(menu)
    
    # Generate and save the RSS feed
    generate_rss(today_menus)
