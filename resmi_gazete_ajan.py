#!/usr/bin/env python3
"""
Resmi Gazete Vergi / Maliye İzleme Ajanı
- Bugünün fihristini tarar, anahtar kelimelere uyanları bulur
- docs/index.html (telefonda açılan site) üretir
- Yeni bulunanları ntfy ile iPhone'a bildirir

Ortam değişkenleri (hepsi opsiyonel):
  NTFY_TOPIC  -> ntfy konu adı (tahmin edilemez bir isim seç)
  SITE_URL    -> GitHub Pages adresin (bildirime tıklayınca açılır)
"""
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.resmigazete.gov.tr"
HISTORY = Path("history.json")
OUT = Path("docs/index.html")

KEYWORDS = [
    "hazine ve maliye bakanlığı", "maliye bakanlığı", "gelir idaresi",
    "vergi", "katma değer", "kdv", "özel tüketim", "ötv", "damga",
    "harçlar", "gelir vergisi", "kurumlar vergisi", "vergi usul",
    "gümrük", "stopaj", "muhasebat", "e-fatura", "e-defter",
    "yeniden değerleme", "vergi dairesi", "ticari kazanç",
]


def norm(t: str) -> str:
    return t.replace("İ", "i").replace("I", "ı").lower().strip()


def fetch_items(date):
    r = requests.get(f"{BASE}/fihrist?tarih={date:%Y-%m-%d}", timeout=30,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(title) < 8:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = BASE + href
        items.append((title, href))
    return items


def matches(title):
    t = norm(title)
    return [k for k in KEYWORDS if norm(k) in t]


def load_history():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return []


def render(history, now):
    rows, last = [], None
    for h in sorted(history, key=lambda x: x["date"], reverse=True):
        if h["date"] != last:
            d = datetime.strptime(h["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
            rows.append(f"<h2>{d}</h2>")
            last = h["date"]
        rows.append(
            f'<a class="card" href="{html.escape(h["link"])}">'
            f'<span>{html.escape(h["title"])}</span>'
            f'<small>{html.escape(", ".join(h["kw"]))}</small></a>'
        )
    body = "\n".join(rows) or "<p>Henüz eşleşme yok.</p>"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Resmi Gazete – Vergi/Maliye</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--card:#f3f4f6;--mut:#666}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--card:#1e1e1e;--mut:#999}}}}
body{{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg);
margin:0;padding:16px;max-width:700px;margin:auto}}
h1{{font-size:20px}} h2{{font-size:15px;color:var(--mut);margin:22px 0 8px}}
.card{{display:block;background:var(--card);padding:12px;border-radius:12px;margin:8px 0;
text-decoration:none;color:inherit}}
.card small{{display:block;color:var(--mut);margin-top:4px}}
</style></head><body>
<h1>📰 Resmi Gazete – Vergi/Maliye</h1>
<p style="color:var(--mut);font-size:13px">Son kontrol: {now:%d.%m.%Y %H:%M}</p>
{body}
</body></html>""", encoding="utf-8")


def notify(hits):
    topic = os.getenv("NTFY_TOPIC")
    text = "\n".join(f"• {t}" for t, _, _ in hits)
    if not topic:
        print("[NTFY_TOPIC yok]\n", text)
        return
    headers = {"Title": "Resmi Gazete - Vergi/Maliye", "Tags": "newspaper"}
    site = os.getenv("SITE_URL")
    click = site or hits[0][1]
    headers["Click"] = click
    requests.post(f"https://ntfy.sh/{topic}", data=text[:3500].encode("utf-8"),
                  headers=headers, timeout=30).raise_for_status()


def main():
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    history = load_history()
    seen = {(h["date"], h["link"]) for h in history}

    try:
        items = fetch_items(now)
    except Exception as e:
        print("Hata:", e, file=sys.stderr)
        sys.exit(1)

    new = []
    for title, link in items:
        kw = matches(title)
        key = (f"{now:%Y-%m-%d}", link)
        if kw and key not in seen:
            seen.add(key)
            history.append({"date": key[0], "title": title, "link": link, "kw": kw})
            new.append((title, link, kw))

    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    render(history, now)
    if new:
        notify(new)
    print(f"{len(new)} yeni eşleşme.")


if __name__ == "__main__":
    main()
