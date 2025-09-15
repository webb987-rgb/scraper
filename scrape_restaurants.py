import asyncio
import re
import json
import datetime
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, urljoin
import pandas as pd
import matplotlib.pyplot as plt
from playwright.async_api import async_playwright

# -------- Konfiguracija --------
WOLT_HOME = "https://wolt.com/sr/srb"  # Promenjeno na sr/srb
WOLT_RESTAURANTS = "https://wolt.com/en/discovery/restaurants"
GLOVO_HOME = "https://glovoapp.com/en/rs"  # Promenjeno na en/rs
GLOVO_RESTAURANTS = "https://glovoapp.com/rs/sr/nis/restorani_1/"
OUTPUT_DIR = Path("./reports")
OUTPUT_DIR.mkdir(exist_ok=True)
HEADLESS = True

SCROLL_PAUSE = 2.0
MIN_SCROLLS_PER_ADDR = 10
MAX_SCROLL_EXTRA = 40
STABLE_ROUNDS = 3
GLOVO_MAX_PAGES = 5

ADDRESSES = [
    "Svetozara Markovica 30, Niš",
    "Knjazevacka 148, Niš",
    "Studenička 65, Niš",
    "Rudnička 1, Niš",
    "Radmile Kovacevic 3, Niš",
    "Bulevar 12. februara 35, Niš",
    "Đerdapska 45, Niš",
]

# -------- Helperi --------
def timestamp():
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def normalize_link(href, base=None):
    if not href:
        return None
    href = href.strip()
    if base:
        href = urljoin(base, href)
    parsed = urlparse(href)
    path = parsed.path.rstrip("/")
    norm = f"{parsed.scheme}://{parsed.netloc}{path}"
    return norm

def is_wolt_restaurant_url(href):
    if not href:
        return False
    try:
        p = urlparse(href)
    except Exception:
        return False
    netloc = p.netloc.lower()
    if "wolt.com" not in netloc:
        return False
    path = p.path.lower()
    if re.search(r'/categories|/collections|/search|/category', path):
        return False
    if re.search(r'/venue/|/restaurant/|/restaurants/', path):
        return True
    return False

def is_glovo_restaurant_path(href):
    if not href:
        return False
    path = href.split("?")[0].rstrip("/").lower()
    if not path.startswith("/rs/sr/nis/"):
        return False
    if "restorani" in path:
        return False
    after = path[len("/rs/sr/nis/"):]
    if "/" in after:
        return False
    if len(after) < 2:
        return False
    return True

# -------- Adrese --------
async def set_wolt_address_from_home(page, address):
    try:
        print(f"🔵 Wolt: Postavljam adresu: {address}")
        await page.goto(WOLT_HOME, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Prihvati kolačiće
        try:
            allow_button = page.locator('[data-test-id="allow-button"]')
            await allow_button.click(timeout=5000)
            await asyncio.sleep(2)
        except:
            print("⚠️ Wolt: Nije pronađeno dugme za kolačiće")

        # Pronađi i klikni na search box
        search_box = page.get_by_role('combobox', name='Unesite adresu za isporuku')
        await search_box.click(timeout=10000)
        await asyncio.sleep(1)
        
        # Unesi adresu
        await search_box.fill(address)
        await asyncio.sleep(2)  # Čekaj za sugestije

        # Klikni na sugestiju
        try:
            suggestion = page.get_by_text('Niš, Србија').first
            await suggestion.click(timeout=5000)
            await asyncio.sleep(3)
        except:
            print("⚠️ Wolt: Nije pronađena sugestija, pokušavam Enter")
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

        # Klikni na Restaurants tab
        try:
            restaurants_tab = page.get_by_role("tab", name="Restorani")
            await restaurants_tab.click(timeout=5000)
            await asyncio.sleep(3)
            print("✅ Wolt: Adresa uspešno postavljena")
            return True
        except Exception as e:
            print(f"⚠️ Wolt: Greška pri klikanju na Restaurants tab: {e}")
            # Probaj direktno da ideš na restaurants stranicu
            await page.goto(WOLT_RESTAURANTS, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            return True
            
    except Exception as e:
        print(f"❌ Wolt: Greška pri navigaciji: {e}")
        return False

async def set_glovo_address_from_home(page, address):
    try:
        print(f"🟡 Glovo: Postavljam adresu: {address}")
        await page.goto(GLOVO_HOME, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Prihvati kolačiće
        try:
            await page.get_by_role("button", name="Accept All").click(timeout=5000)
            await asyncio.sleep(2)
        except:
            print("⚠️ Glovo: Nije pronađeno dugme za kolačiće 'Accept All'")

        # Klikni na address input - više opcija za različite UI
        try:
            await page.locator("#hero-container-input").get_by_role("textbox", name="What's your address?").click(timeout=5000)
        except:
            try:
                await page.get_by_role("textbox", name="Search").click(timeout=5000)
            except:
                print("⚠️ Glovo: Nije pronađeno polje za pretragu")
                return False

        await asyncio.sleep(1)
        
        # Unesi adresu
        await page.get_by_role("textbox", name="Search").fill(address)
        await asyncio.sleep(2)  # Čekaj za sugestije

        # Klikni na sugestiju - sačekaj da se pojave sugestije
        try:
            # Sačekaj da se pojave sugestije
            await page.wait_for_selector('[class*="ListItemBody_pintxo-list-item"]', timeout=5000)
            
            # Pronađi tačnu sugestiju za Đerdapska 45
            suggestions = page.locator('[class*="ListItemBody_pintxo-list-item"]')
            count = await suggestions.count()
            
            found = False
            for i in range(count):
                text = await suggestions.nth(i).text_content()
                # Tražimo tačno "Đerdapska" i "45" u sugestiji
                if ("đerdapska" in text.lower() or "derdapska" in text.lower()) and "45" in text:
                    # Klikni na ovu sugestiju
                    await suggestions.nth(i).click()
                    print("✅ Glovo: Izabrana tačna adresa Đerdapska 45 iz sugestija")
                    found = True
                    break
            
            if not found:
                # Ako nije pronađena tačna, tražimo bilo koju sa "Niš, Serbia"
                for i in range(count):
                    text = await suggestions.nth(i).text_content()
                    if "niš, serbia" in text.lower() or "nis, serbia" in text.lower():
                        await suggestions.nth(i).click()
                        print("✅ Glovo: Izabrana adresa za Niš")
                        found = True
                        break
            
            if not found:
                # Ako ništa nije pronađeno, uzmi prvu sugestiju
                await suggestions.first.click()
                print("✅ Glovo: Izabrana prva sugestija")
                
        except Exception as e:
            print(f"⚠️ Glovo: Greška pri odabiru sugestije: {e}")
            # Fallback: Enter
            await page.keyboard.press("Enter")
        
        await asyncio.sleep(2)

        # Izaberi tip objekta
        address_types = ["House", "Apartment", "Other", "Kuća", "Stan", "Ostalo"]
        for option in address_types:
            try:
                await page.get_by_role("button", name=option).click(timeout=2000)
                print(f"✅ Glovo: Izabran tip objekta: {option}")
                await asyncio.sleep(1)
                break
            except:
                continue

        # Potvrdi adresu
        try:
            confirm_selectors = [
                'button:has-text("Confirm address")',
                'button:has-text("Potvrdi adresu")',
                '[data-test-id="confirm-address-button"]'
            ]
            
            for selector in confirm_selectors:
                try:
                    await page.locator(selector).click(timeout=3000)
                    break
                except:
                    continue
                    
            await asyncio.sleep(3)
        except:
            print("⚠️ Glovo: Nije pronađeno dugme za potvrdu adrese")

        # Idi na restorane
        await page.goto(GLOVO_RESTAURANTS, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print("✅ Glovo: Adresa uspešno postavljena")
        return True

    except Exception as e:
        print(f"❌ Glovo: Greška pri setovanju adrese: {e}")
        # Snimi screenshot za debug
        await page.screenshot(path="glovo_error.png")
        return False

# -------- Scraping --------
async def scrape_wolt_per_address(page):
    collected = set()
    prev_count = 0
    stable_count = 0
    
    # Proveri da li smo na restaurants stranici
    current_url = page.url
    if "restaurants" not in current_url.lower():
        print("⚠️ Wolt: Nismo na restaurants stranici, preusmeravam...")
        await page.goto(WOLT_RESTAURANTS, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
    
    for i in range(MIN_SCROLLS_PER_ADDR):
        all_links = await page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
        for href in all_links:
            if href and is_wolt_restaurant_url(href):
                norm = normalize_link(href)
                if norm:
                    collected.add(norm)
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(SCROLL_PAUSE)
    
    extra = 0
    while extra < MAX_SCROLL_EXTRA:
        all_links = await page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
        for href in all_links:
            if href and is_wolt_restaurant_url(href):
                norm = normalize_link(href)
                if norm:
                    collected.add(norm)
        
        if len(collected) == prev_count:
            stable_count += 1
        else:
            stable_count = 0
        prev_count = len(collected)
        
        if stable_count >= STABLE_ROUNDS:
            break
            
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(SCROLL_PAUSE)
        extra += 1
    
    print(f"✅ Wolt: Pronađeno {len(collected)} restorana")
    return sorted(collected)

async def scrape_glovo_per_address(page):
    collected = set()
    
    # Proveri da li smo na restaurants stranici
    current_url = page.url
    if "restorani" not in current_url.lower():
        print("⚠️ Glovo: Nismo na restaurants stranici, preusmeravam...")
        await page.goto(GLOVO_RESTAURANTS, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
    
    for p in range(1, GLOVO_MAX_PAGES + 1):
        url = f"{GLOVO_RESTAURANTS}?page={p}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"⚠️ Glovo: Greška pri navigaciji na stranicu {p}: {e}")
            continue
            
        hrefs = await page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href') || '')")
        for h in hrefs:
            if not h:
                continue
            if h.startswith("/"):
                full = urljoin("https://glovoapp.com", h)
            elif h.startswith("http"):
                full = h
            else:
                full = urljoin("https://glovoapp.com", "/" + h)
                
            if is_glovo_restaurant_path(h) or is_glovo_restaurant_path(full):
                norm = normalize_link(full)
                if norm:
                    collected.add(norm)
    
    print(f"✅ Glovo: Pronađeno {len(collected)} restorana")
    return sorted(collected)

# -------- Parallel scraping --------
async def scrape_address(context, addr, platform):
    page = await context.new_page()
    result = {"address": addr, "wolt": [], "glovo": []}
    try:
        if platform == "glovo":
            if await set_glovo_address_from_home(page, addr):
                result["glovo"] = await scrape_glovo_per_address(page)
        elif platform == "wolt":
            if await set_wolt_address_from_home(page, addr):
                result["wolt"] = await scrape_wolt_per_address(page)
    except Exception as e:
        print(f"❌ Greška pri scrapingu {platform} za adresu {addr}: {e}")
    finally:
        await page.close()
    return result

async def scrape_all_parallel(addresses):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context()
        tasks = []
        for addr in addresses:
            tasks.append(scrape_address(context, addr, "glovo"))
            tasks.append(scrape_address(context, addr, "wolt"))
        results = await asyncio.gather(*tasks)
        await browser.close()
        return results

# -------- Save reports --------
def save_reports(results):
    date = timestamp()
    out_html = OUTPUT_DIR / f"report_{date}.html"
    out_csv = OUTPUT_DIR / f"report_{date}.csv"
    out_png = OUTPUT_DIR / f"report_{date}_bar.png"

    rows = []
    total_wolt = set()
    total_glovo = set()
    for r in results:
        rows.append({"address": r["address"], "wolt_count": len(r["wolt"]), "glovo_count": len(r["glovo"])})
        total_wolt.update(r["wolt"])
        total_glovo.update(r["glovo"])
    pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8")

    plt.figure(figsize=(6, 4))
    plt.bar(["Wolt", "Glovo"], [len(total_wolt), len(total_glovo)])
    plt.title(f"Broj restorana - {date}")
    plt.savefig(out_png, bbox_inches="tight")
    plt.close()

    html = f"<html><head><meta charset='utf-8'></head><body><h1>Report {date}</h1>"
    for r in rows:
        html += f"<p>{r['address']}: Wolt {r['wolt_count']} - Glovo {r['glovo_count']}</p>"
    html += f"<h2>Ukupno</h2><p>Wolt {len(total_wolt)} | Glovo {len(total_glovo)}</p>"
    html += f"<img src='{out_png.name}'></body></html>"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    return out_html

# -------- Main --------
async def main():
    print("🚀 Počinjem scraping...")
    results = await scrape_all_parallel(ADDRESSES)
    out_html = save_reports(results)
    print(f"✅ Scraping završen. Rezultati sačuvani u: {out_html}")
    webbrowser.open(f"file://{os.path.abspath(out_html)}")

if __name__ == "__main__":

    asyncio.run(main())
