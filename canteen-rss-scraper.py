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
FEED_URL = "https://arctoz00.github.io/canteen-rss-feed/feed.xml"  # Opdater hvis nødvendigt
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
        wait = WebDriverWait(driver, 60)
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
    Returnerer en dict med format:
       { hub_navn: { dag (i små bogstaver): [liste af menu-tekster] } }

    Ændringer:
    - HUB1 – Kays Verdenskøkken er en selvstændig hub (hvis headeren indeholder "hub1" og "verdenskøkken").
    - "GLOBETROTTER MENU" og "Vegetar" tilføjes som daglige menuer (mandag-fredag).
    - "Onsdag" tilføjes kun på "onsdag".
    - Andre eksplicitte dage (mandag, tirsdag osv.) håndteres sædvanligt.
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

        # Skel HUB1 i to varianter
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
            continue  # Hvis ikke HUB1, HUB2 eller HUB3, spring over

        block_menus = {}
        current_day = None

        # Disse to lister vil blive lagt som "daglige menuer" (mandag-fredag)
        daily_items = []
        # Linjer specifikt for onsdag
        wednesday_items = []

        for p in div.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            candidate = text.replace(":", "").strip().lower()

            if candidate in valid_days:
                # Hvis fx "mandag", "tirsdag" osv. – sæt current_day
                current_day = candidate
                if current_day not in block_menus:
                    block_menus[current_day] = []
            else:
                # Hvis teksten er "globetrotter menu" eller "vegetar" => daglige menuer
                if "globetrotter menu" in candidate or "vegetar" in candidate:
                    daily_items.append(text)
                # Hvis teksten præcis matcher "onsdag"
                elif candidate == "onsdag":
                    # Linjer herefter betragtes som "onsdag"?
                    # For at matche brugens ønske, tilføjer vi bare et dagstegn for "onsdag".
                    current_day = "onsdag"
                    if current_day not in block_menus:
                        block_menus[current_day] = []
                else:
                    # Hvis vi har et aktivt day, tilføj til day-liste
                    if current_day:
                        block_menus[current_day].append(text)
                    else:
                        # Ellers gem i daily_items (hvis du ønsker alt uden dag at være "dagligt")
                        daily_items.append(text)

        # Hvis block_menus er tomt og hub_name starter med "HUB1", antag daily
        if not block_menus and hub_name.startswith("HUB1") and daily_items:
            block_menus = { day: daily_items.copy() for day in daily_days }
        else:
            # Ellers læg daily_items til mandag-fredag
            for d in daily_days:
                if d not in block_menus:
                    block_menus[d] = []
                block_menus[d].extend(daily_items)

        # Merge block_menus med overordnede data
        if hub_name in menus_by_hub:
            for day, items in block_menus.items():
                if day in menus_by_hub[hub_name]:
                    menus_by_hub[hub_name][day].extend(items)
                else:
                    menus_by_hub[hub_name][day] = items
        else:
            menus_by_hub[hub_name] = block_menus

    return menus_by_hub

def get_today_menus(menus_by_hub):
    """
    Finder dagens menu for hver hub ud fra de ugentlige data.
    Returnerer en liste med formatet "HUB-navn: menu".
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
            joined_text = " | ".join(menu_dict[today_da])
            today_menus.append(f"{hub}: {joined_text}")

    return today_menus

def generate_rss(menu_items):
    """
    Genererer et RSS-feed med et <item> per hub og gemmer det i RSS_FILE.
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

    # Generer RSS-XML
    rss_bytes = fg.rss_str(pretty=True)
    rss_str = rss_bytes.decode("utf-8")

    # Indsæt atom:link og docs
    atom_link_str = f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>\n'
    rss_str = rss_str.replace("<channel>", "<channel>\n" + atom_link_str, 1)
    docs_str = '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
    rss_str = rss_str.replace(atom_link_str, atom_link_str + docs_str, 1)

    # Erstat evt. escaped CDATA
    rss_str = rss_str.replace("&lt;![CDATA[", "<![CDATA[").replace("]]&gt;", "]]>")

    # Tilføj isPermaLink="false" og CDATA til guid
    rss_str = re.sub(r'<guid>(.*?)</guid>', r'<guid isPermaLink="false"><![CDATA[\1]]></guid>', rss_str)

    # Wrap channel title og description i CDATA
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
