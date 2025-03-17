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
        wait = WebDriverWait(driver, 60)  # Øger timeout til 60 sekunder
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.et_pb_text_inner")))
    except Exception as e:
        print("Timed out waiting for content to load:", e)
    time.sleep(2)
    html = driver.page_source
    driver.quit()
    return html

def scrape_weekly_menus():
    """
    Parser den fuldt renderede HTML og udtrækker de ugentlige menuer for hver hub.
    Returnerer en dict med formatet:
       { hub_navn: { dag (i små bogstaver): [liste af menu-tekster] } }
    Hvis samme hub optræder flere gange, merges dataene.
    
    Ændringer:
      - HUB1 opdeles nu i to separate hubs:
          "HUB1 – Kays" og "HUB1 – Kays Verdenskøkken" (afhængigt af om headeren indeholder "verdenskøkken").
      - "GLOBETROTTER MENU" og "Vegetar" (og lignende) bliver til de daglige menuer.
      - Hvis der ikke findes et eksplicit dagstegn, tilføjes disse menuer kun én gang pr. dag (mandag til fredag).
    """
    html = get_rendered_html()
    soup = BeautifulSoup(html, "html.parser")
    
    hub_divs = soup.find_all("div", class_="et_pb_text_inner")
    menus_by_hub = {}
    valid_days = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    daily_days = ['mandag','tirsdag','onsdag','torsdag','fredag']
    
    for div in hub_divs:
        header = div.find("h4")
        if not header:
            continue
        
        raw_header = header.get_text(separator=" ", strip=True)
        lower_header = raw_header.lower()
        
        # Bestem hub-navnet
        if "hub1" in lower_header:
            if "verdenskøkken" in lower_header:
                hub_name = "HUB1 – Kays Verdenskøkken"
            else:
                hub_name = "HUB1 – Kays"
        elif "hub2" in lower_header or "hu b2" in lower_header:
            hub_name = "HUB2"
        elif "hub3" in lower_header:
            hub_name = "HUB3"
        else:
            continue
        
        block_menus = {}
        current_day = None
        collected_items = []  # Samler menuer, der ikke er knyttet til en specifik dag
        
        for p in div.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            candidate = text.replace(":", "").strip().lower()
            # Hvis teksten præcist matcher en dag (f.eks. "mandag")
            if candidate in valid_days:
                current_day = candidate
                if current_day not in block_menus:
                    block_menus[current_day] = []
            else:
                # Hvis teksten indeholder "globetrotter menu" eller "vegetar", antag at det er en daglig menu
                if "globetrotter menu" in candidate or "vegetar" in candidate:
                    # Tilføj til daily_items, men undgå dublering
                    if text not in collected_items:
                        collected_items.append(text)
                else:
                    if current_day:
                        block_menus[current_day].append(text)
                    else:
                        if text not in collected_items:
                            collected_items.append(text)
        
        # Hvis der ikke er fundet specifikke dage, og vi har collected_items (daglige menuer)
        if not block_menus and collected_items:
            block_menus = { day: collected_items.copy() for day in daily_days }
        else:
            # For alle dage (mandag-fredag) tilføjes de daily_items, men undgå dublering
            for d in daily_days:
                if d not in block_menus:
                    block_menus[d] = collected_items.copy()
                else:
                    for item in collected_items:
                        if item not in block_menus[d]:
                            block_menus[d].append(item)
        
        # Merge block_menus med overordnet dictionary
        if hub_name in menus_by_hub:
            for day, items in block_menus.items():
                if day in menus_by_hub[hub_name]:
                    menus_by_hub[hub_name][day].extend(items)
                else:
                    menus_by_hub[hub_name][day] = items
        else:
            menus_by_hub[hub_name] = block_menus

    # De-duplikér alle lister for at sikre, at ingen dubleringer forekommer
    for hub in menus_by_hub:
        for day in menus_by_hub[hub]:
            # Brug dict.fromkeys for at fjerne dubletter mens rækkefølgen bevares
            menus_by_hub[hub][day] = list(dict.fromkeys(menus_by_hub[hub][day]))
    
    return menus_by_hub

def get_today_menus(menus_by_hub):
    """
    Udtrækker dagens menu for hver hub (HUB1 – Kays, HUB1 – Kays Verdenskøkken, HUB2, HUB3)
    ud fra de ugentlige data. Returnerer en liste med én streng per hub, f.eks. "HUB2: menu-text".
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
    for hub, menu_dict in menus_by_hub.items():
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
    
    # Generer RSS XML-streng
    rss_bytes = fg.rss_str(pretty=True)
    rss_str = rss_bytes.decode("utf-8")
    
    # Indsæt manuelt et <atom:link> element lige efter <channel>
    atom_link_str = f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>\n'
    rss_str = rss_str.replace("<channel>", "<channel>\n" + atom_link_str, 1)
    
    # Indsæt et <docs> element lige efter <atom:link>
    docs_str = '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
    rss_str = rss_str.replace(atom_link_str, atom_link_str + docs_str, 1)
    
    # Sørg for, at CDATA ikke er escaped
    rss_str = rss_str.replace("&lt;![CDATA[", "<![CDATA[").replace("]]&gt;", "]]>")
    
    # Tilføj isPermaLink="false" til alle <guid> elementer og omslut med CDATA
    rss_str = re.sub(r'<guid>(.*?)</guid>', r'<guid isPermaLink="false"><![CDATA[\1]]></guid>', rss_str)
    
    # Wrap channel title and description with CDATA (kun én gang)
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
