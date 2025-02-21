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

MENU_URL = "https://hubnordic.madkastel.dk/"
RSS_FILE = "feed.xml"

def get_rendered_html():
    """
    Loads the webpage via Selenium in headless mode and returns rendered HTML.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)
    
    driver.get(MENU_URL)
    try:
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    time.sleep(2)
    
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parses the rendered HTML and extracts weekly menus for each hub.
    Returns a dict of the form:
      { hub_name: { day_in_lowercase: [list of menu items] } }
    If a hub appears multiple times, merges the data.
    """
    html = get_rendered_html()
    soup = BeautifulSoup(html, "html.parser")
    
    hub_divs = soup.find_all("div", class_="et_pb_text_inner")
    menus_by_hub = {}
    valid_days = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    
    for div in hub_divs:
        header = div.find("h4")
        if not header:
            continue
        hub_header_text = header.get_text(separator=" ", strip=True)
        
        # Normalize hub name
        if "hub1" in hub_header_text.lower():
            hub_name = "HUB1 – Kays Verdenskøkken"
        elif "hu b2" in hub_header_text.lower() or "hub2" in hub_header_text.lower():
            hub_name = "HUB2"
        elif "hub3" in hub_header_text.lower():
            hub_name = "HUB3"
        else:
            hub_name = hub_header_text
        
        hub_menus = {}
        current_day = None
        
        for p in div.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            candidate = text.replace(":", "").strip().lower()
            if any(day in candidate for day in valid_days):
                for day in valid_days:
                    if day in candidate:
                        current_day = day
                        break
                if current_day and current_day not in hub_menus:
                    hub_menus[current_day] = []
            else:
                if current_day:
                    hub_menus[current_day].append(text)
        
        # Merge if hub_name already in dict
        if hub_name in menus_by_hub:
            for day, items in hub_menus.items():
                if day in menus_by_hub[hub_name]:
                    menus_by_hub[hub_name][day].extend(items)
                else:
                    menus_by_hub[hub_name][day] = items
        else:
            menus_by_hub[hub_name] = hub_menus

    return menus_by_hub

def get_today_menus(menus_by_hub):
    """
    Extracts today's menu for each hub (HUB1, HUB2, HUB3).
    Returns a list of strings, e.g., "HUB2: some menu text".
    """
    weekday_map = {
        "Monday": "mandag",
        "Tuesday": "tirsdag",
        "Wednesday": "onsdag",
        "Thursday": "torsdag",
        "Friday": "fredag",
        "Saturday": "lørdag",
        "Sunday": "søndag"
    }
    today_en = datetime.datetime.today().strftime("%A")
    today_da = weekday_map.get(today_en, "").lower()
    
    print("Systemets dag (engelsk):", today_en)
    print("Mapper til (dansk):", today_da)
    
    allowed_hubs = ["hub1","hub2","hub3"]
    today_menus = []
    
    for hub, menu_dict in menus_by_hub.items():
        if not any(keyword in hub.lower() for keyword in allowed_hubs):
            continue
        if today_da in menu_dict and menu_dict[today_da]:
            menu_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {menu_text}")
    
    return today_menus

def generate_rss(menu_items):
    """
    Creates an RSS feed with one <item> per hub. Uses feedgen's atom extension
    to add <atom:link>. Avoids using fg._elem references.
    """
    fg = FeedGenerator()
    # Load the atom extension to add atom:link
    fg.load_extension('atom')
    
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    fg.title(f"Canteen Menu - {today_str}")
    fg.link(href=MENU_URL)
    fg.description("Dagligt opdateret canteen-menu")
    fg.language("da")
    fg.lastBuildDate(datetime.datetime.now(pytz.utc))
    
    # Official atom_link usage
    fg.atom_link({
        'href': MENU_URL,
        'rel': 'self',
        'type': 'application/rss+xml'
    })
    
    # Create one RSS item for each hub in menu_items
    for i, item in enumerate(menu_items):
        parts = item.split(":", 1)
        if len(parts) < 2:
            continue
        hub_name = parts[0].strip()
        hub_menu = parts[1].strip()
        
        entry = fg.add_entry()
        entry.title(hub_name)
        entry.link(href=MENU_URL)
        entry.description(hub_menu)
        entry.pubDate(datetime.datetime.now(pytz.utc))
        
        guid_value = f"urn:canteen:{hub_name.replace(' ', '').lower()}-{datetime.datetime.now().strftime('%Y%m%d')}-{i}"
        entry.guid(guid_value, isPermaLink=False)
    
    # Save the RSS feed to file
    fg.rss_file(RSS_FILE)
    print("✅ RSS feed opdateret!")

if __name__ == "__main__":
    menus_by_hub = scrape_weekly_menus()
    today_menus = get_today_menus(menus_by_hub)
    print("Dagens menuer:")
    for menu in today_menus:
        print(menu)
    generate_rss(today_menus)
