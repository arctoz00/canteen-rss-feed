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

# URL til canteen-menuen
MENU_URL = "https://hubnordic.madkastel.dk/"
# Vælg filnavn til dit RSS-feed. Hvis du vil have det som et raw RSS-feed, skal det gemmes som XML.
RSS_FILE = "feed.xml"

def get_rendered_html():
    """
    Loader siden med Selenium i headless mode og returnerer den fuldt renderede HTML.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    # Opret ChromeDriver – juster evt. stien, hvis chromedriver.exe ikke er i PATH
    driver = webdriver.Chrome(options=chrome_options)
    
    driver.get(MENU_URL)
    try:
        # Vent til mindst én hub-container (div med klassen "et_pb_text_inner") er tilstede
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    # Ekstra ventetid for at sikre, at alt JavaScript er renderet
    time.sleep(2)
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parser den renderede HTML og udtrækker de ugentlige menuer for hver hub.
    Returnerer en dictionary med formatet:
       { hub_navn: { dag (i små bogstaver): [liste af menu-tekster] } }
    Hvis der findes flere sektioner for samme hub, merges dataene.
    """
    html = get_rendered_html()
    soup = BeautifulSoup(html, "html.parser")
    
    # Find alle hub-containere – de fleste hubs findes i div'er med klassen "et_pb_text_inner"
    hub_divs = soup.find_all("div", class_="et_pb_text_inner")
    menus_by_hub = {}
    
    # Gyldige danske ugedage (i små bogstaver)
    valid_days = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']
    
    for div in hub_divs:
        header = div.find("h4")
        if not header:
            continue
        hub_header_text = header.get_text(separator=" ", strip=True)
        # Normaliser hub-navnet: Hvis teksten indeholder "hub1", "hu b2" eller "hub2" eller "hub3"
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
        
        # Gå igennem alle <p>-elementer i denne hub-container
        for p in div.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            # Fjern kolon og konverter til små bogstaver for at tjekke om det er en dagoverskrift
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
        
        # Hvis huben allerede findes (flere sektioner for samme hub), merge dataene
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
    Udtrækker dagens menu for hver hub ud fra de ugentlige data.
    Returnerer en liste med én streng per hub (kun HUB1, HUB2 og HUB3),
    hvis der faktisk er en menu for den aktuelle dag.
    """
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
    
    print("Systemets dag (engelsk):", today_en)
    print("Mapper til (dansk):", today_da)
    
    today_menus = []
    allowed_keywords = ["hub1", "hub2", "hub3"]
    
    for hub, menu_dict in menus_by_hub.items():
        if not any(keyword in hub.lower() for keyword in allowed_keywords):
            continue
        if today_da in menu_dict and menu_dict[today_da]:
            menu_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {menu_text}")
    return today_menus

def generate_rss(menu_items):
    """
    Genererer et RSS-feed med dagens menuer og gemmer det i RSS_FILE.
    Feedet indeholder separate <item>-elementer for hver hub med titel, link, description, pubDate og guid.
    """
    fg = FeedGenerator()
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    fg.title("Canteen Menu - " + today_str)
    fg.link(href=MENU_URL)
    fg.description("Dagligt opdateret canteen-menu")
    fg.language("da")
    fg.lastBuildDate(datetime.datetime.now(pytz.utc))
    
    # Tilføj et atom:link-element til channel-delen
    atom_link = fg._elem.makeelement("atom:link", {
        "href": MENU_URL,
        "rel": "self",
        "type": "application/rss+xml"
    })
    fg._elem.append(atom_link)
    
    # Opret et item for hver hub (menu_item er på formatet "HUB-navn: menutekst")
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
    
    fg.rss_file(RSS_FILE)
    print("✅ RSS feed opdateret!")

if __name__ == "__main__":
    menus_by_hub = scrape_weekly_menus()
    today_menus = get_today_menus(menus_by_hub)
    print("Dagens menuer:")
    for menu in today_menus:
        print(menu)
    generate_rss(today_menus)
