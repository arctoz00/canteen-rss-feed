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
        
        # Normaliser hub-navnet:
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
            # Fjern kolon og konverter til små bogstaver for at tjekke, om det er en dagoverskrift
            candidate = text.replace(":", "").strip().lower()
            # Hvis candidate indeholder et af de gyldige dagnavne, antages det at være en dagoverskrift
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
    # Mapping fra engelsk til dansk (alle i små bogstaver)
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
        # Inkluder kun de hub'er, hvis navn indeholder et af de allowed_keywords
        if not any(keyword in hub.lower() for keyword in allowed_keywords):
            continue
        if today_da in menu_dict and menu_dict[today_da]:
            menu_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {menu_text}")
        # Hvis der ikke er nogen menu for dagens dag, medtages ikke hub'en
    return today_menus

def generate_rss(menu_items):
    """
    Genererer et RSS-feed med dagens menuer og gemmer det i RSS_FILE.
    Feedet indeholder kun de nødvendige oplysninger: retter fra HUB1, HUB2 og HUB3 samt dato og ugedag.
    """
    fg = FeedGenerator()
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    fg.title("Canteen Menu - " + today_str)
    fg.link(href=MENU_URL)
    fg.description("Dagens retter: " + " | ".join(menu_items))
    fg.language("da")
    
    entry = fg.add_entry()
    entry.title("Dagens menu " + today_str)
    entry.link(href=MENU_URL)
    entry.description(" | ".join(menu_items))
    utc_time = datetime.datetime.now(pytz.utc)
    entry.pubDate(utc_time)
    
    fg.rss_file(RSS_FILE)
    print("✅ RSS feed opdateret!")

if __name__ == "__main__":
    menus_by_hub = scrape_weekly_menus()
    today_menus = get_today_menus(menus_by_hub)
    print("Dagens menuer:")
    for menu in today_menus:
        print(menu)
    generate_rss(today_menus)
