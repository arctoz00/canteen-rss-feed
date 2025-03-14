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
FEED_URL = "https://arctoz00.github.io/canteen-rss-feed/feed.xml"  # Opdater til din faktiske feed-URL
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
        # Øger timeout til 60 sekunder
        wait = WebDriverWait(driver, 60)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    time.sleep(2)  # Ekstra ventetid
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parser den fuldt renderede HTML og udtrækker de ugentlige menuer for hver hub.
    Returnerer en dict med formatet:
       { hub_navn: { dag (i små bogstaver): [liste af menu-tekster] } }
    Hvis samme hub optræder flere gange, merges dataene.
    
    Ændringen for HUB1 – Kays Verdenskøkken:
      - I HUB1-blokke bliver linjer uden eksplicit dagstegn samlet i 'daily_items'
      - Efter blokken tilføjes disse 'daily_items' til alle dage fra mandag til fredag.
      - Linjer med specifikke dagstegn (fx "onsdag") placeres kun under den dag.
    """
    html = get_rendered_html()
    soup = BeautifulSoup(html, "html.parser")
    
    hub_divs = soup.find_all("div", class_="et_pb_text_inner")
    menus_by_hub = {}
    valid_days = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    daily_days = ['mandag','tirsdag','onsdag','torsdag','fredag']  # Dage, der får de "daglige" menuer
    
    for div in hub_divs:
        header = div.find("h4")
        if not header:
            continue
        hub_header_text = header.get_text(separator=" ", strip=True)
        
        # Bestem hub-navnet
        if "hub1" in hub_header_text.lower():
            hub_name = "HUB1 – Kays Verdenskøkken"
        elif "hu b2" in hub_header_text.lower() or "hub2" in hub_header_text.lower():
            hub_name = "HUB2"
        elif "hub3" in hub_header_text.lower():
            hub_name = "HUB3"
        else:
            hub_name = hub_header_text
        
        # For HUB1 laver vi en særlig behandling, så vi kan inkludere "daglige" menuer
        if hub_name == "HUB1 – Kays Verdenskøkken":
            block_menus = {}
            daily_items = []   # Samler menuer, der ikke tilhører en specifik dag (de skal gælde for mandag-fredag)
            current_day = None
            for p in div.find_all("p"):
                text = p.get_text(separator=" ", strip=True)
                lower_text = text.lower().strip()
                # Hvis teksten er en gyldig dag (f.eks. "mandag")
                if lower_text in valid_days:
                    current_day = lower_text
                    block_menus[current_day] = []
                # Hvis teksten er en header for en daglig menu (fx "globetrotter menu", "homebound menu", eller "vegetar")
                elif lower_text in ["globetrotter menu", "homebound menu", "vegetar"]:
                    # Vi markerer, at efterfølgende linjer hører til de daglige menuer (hvis ingen specifik dag er angivet)
                    current_day = None  # Nulstil, så vi ikke tilknytter linjer til en specifik dag
                else:
                    # Hvis vi har en specifik dag, tilføjes teksten til den dag
                    if current_day:
                        block_menus[current_day].append(text)
                    else:
                        # Hvis der ikke er et aktivt dagstegn, betragtes teksten som en del af de daglige menuer
                        daily_items.append(text)
            # Tilføj daily_items til alle dagene mandag-fredag
            for d in daily_days:
                if d in block_menus:
                    block_menus[d].extend(daily_items)
                else:
                    block_menus[d] = daily_items.copy()
            # Gem block_menus for HUB1
            if hub_name in menus_by_hub:
                # Merge med eksisterende data
                for day, items in block_menus.items():
                    if day in menus_by_hub[hub_name]:
                        menus_by_hub[hub_name][day].extend(items)
                    else:
                        menus_by_hub[hub_name][day] = items
            else:
                menus_by_hub[hub_name] = block_menus
        else:
            # For HUB2 og HUB3, benyt den eksisterende metode
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
    Returnerer en liste med én streng per hub, f.eks. "HUB2: menu-text".
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
      - <description> (hub-menu) omsluttet af CDATA
      - <pubDate> i RFC-822 format
      - <guid> med attribut isPermaLink="false"
    Channel-elementet indeholder metadata inkl. et <atom:link> og et <docs>-element.
    """
    fg = FeedGenerator()
    today_str = datetime.date.today().strftime("%A, %d %B %Y")
    
    # Channel metadata
    fg.title(f"Canteen Menu - {today_str}")
    fg.link(href=MENU_URL)
    fg.description("Dagligt opdateret canteen-menu")
    fg.language("da")
    fg.lastBuildDate(datetime.datetime.now(pytz.utc))
    fg.generator("Python feedgen")
    fg.ttl(15)
    fg.docs("http://www.rssboard.org/rss-specification")
    
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
        clean_hub_name = re.sub(r"\s+", "", hub_name).lower()
        guid_value = f"urn:canteen:{clean_hub_name}-{datetime.datetime.now().strftime('%Y%m%d')}-{i}"
        entry.guid(guid_value)
    
    # Generate RSS XML string
    rss_bytes = fg.rss_str(pretty=True)
    rss_str = rss_bytes.decode("utf-8")
    
    # Insert <atom:link> element manually right after <channel>
    atom_link_str = f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>\n'
    rss_str = rss_str.replace("<channel>", "<channel>\n" + atom_link_str, 1)
    
    # Insert <docs> element right after <atom:link>
    docs_str = '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
    rss_str = rss_str.replace(atom_link_str, atom_link_str + docs_str, 1)
    
    # Ensure CDATA sections are not escaped
    rss_str = rss_str.replace("&lt;![CDATA[", "<![CDATA[").replace("]]&gt;", "]]>")
    
    # Add isPermaLink="false" to all <guid> elements and wrap with CDATA
    rss_str = re.sub(r'<guid>(.*?)</guid>', r'<guid isPermaLink="false"><![CDATA[\1]]></guid>', rss_str)
    
    # Wrap channel title and description with CDATA (only once)
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