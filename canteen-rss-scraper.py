import time
import datetime
import pytz
import re
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
    Loader siden med Selenium i headless mode og returnerer den fuldt renderede HTML.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)
    
    driver.get(MENU_URL)
    try:
        wait = WebDriverWait(driver, 60)  # Øger timeout for at sikre, at siden loader helt
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    time.sleep(2)
    
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parser den renderede HTML og udtrækker de ugentlige menuer for hver hub.
    Returnerer en dictionary med formatet:
       { hub_navn: { dag (i små bogstaver): [liste af menu-tekster] } }
    Hvis samme hub optræder flere gange, merges dataene.
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
    Udtrækker dagens menu for hver hub (kun HUB1, HUB2 og HUB3) ud fra de ugentlige data.
    Returnerer en liste med én streng per hub, fx "HUB2: menu-text".
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
    
    allowed_keywords = ["hub1", "hub2", "hub3"]
    today_menus = []
    
    for hub, menu_dict in menus_by_hub.items():
        if not any(keyword in hub.lower() for keyword in allowed_keywords):
            continue
        if today_da in menu_dict and menu_dict[today_da]:
            menu_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {menu_text}")
    return today_menus

def generate_rss(menu_items):
    """
    Genererer et RSS-feed med et <item> per hub og gemmer det i RSS_FILE.
    Hvert item indeholder:
      - <title> (hub-navn) omsluttet af CDATA
      - <link> (MENU_URL)
      - <guid> (unik, med isPermaLink="false")
      - <pubDate> (i RFC-822 format)
      - <description> (hub-menu) omsluttet af CDATA
    Channel-elementet indeholder også metadata, herunder et <atom:link>.
    """
    fg = FeedGenerator()
    
    # Channel metadata
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    fg.title(f"Canteen Menu - {today_str}")
    fg.link(href=MENU_URL)
    fg.description("Dagligt opdateret canteen-menu")
    fg.language("da")
    fg.lastBuildDate(datetime.datetime.now(pytz.utc))
    fg.generator("Python feedgen")
    fg.ttl(15)
    
    # Vi genererer items for hvert hub i menu_items
    for i, item in enumerate(menu_items):
        parts = item.split(":", 1)
        if len(parts) < 2:
            continue
        hub_name = parts[0].strip()
        hub_menu = parts[1].strip()
        entry = fg.add_entry()
        entry.title(f"<![CDATA[{hub_name}]]>")
        entry.link(href=MENU_URL)
        entry.description(f"<![CDATA[{hub_menu}]]>")
        entry.pubDate(datetime.datetime.now(pytz.utc))
        guid_value = f"urn:canteen:{hub_name.replace(' ', '').lower()}-{datetime.datetime.now().strftime('%Y%m%d')}-{i}"
        # Vi skal inkludere isPermaLink="false" manuelt i den genererede XML
        entry.guid(guid_value)
    
    # Generer den rå RSS XML-streng med pretty-print
    rss_bytes = fg.rss_str(pretty=True)
    rss_str = rss_bytes.decode("utf-8")
    
    # Tilføj manuelt et <atom:link> element under <channel>
    atom_link_str = f'    <atom:link href="{MENU_URL}" rel="self" type="application/rss+xml"/>\n'
    rss_str = rss_str.replace("<channel>", "<channel>\n" + atom_link_str, 1)
    
    # Wrap guid tags with attribute isPermaLink="false" manuelt
    # Find alle guid tags og tilføj attributten, hvis den ikke allerede er tilstede
    rss_str = re.sub(r'<guid>(.*?)</guid>', r'<guid isPermaLink="false">\1</guid>', rss_str)
    
    # Optional: Wrap channel title and description with CDATA
    rss_str = re.sub(r'<title>(.*?)</title>', r'<title><![CDATA[\1]]></title>', rss_str, count=1)
    rss_str = re.sub(r'<description>(.*?)</description>', r'<description><![CDATA[\1]]></description>', rss_str, count=1)
    
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(rss_str)
    print("✅ RSS feed opdateret!")

if __name__ == "__main__":
    menus_by_hub = scrape_weekly_menus()
    today_menus = get_today_menus(menus_by_hub)
    print("Dagens menuer:")
    for menu in today_menus:
        print(menu)
    generate_rss(today_menus)
