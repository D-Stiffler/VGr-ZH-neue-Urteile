import os
import re
import html
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import pytz

# -------- Settings --------
BASE_URL = "https://vgrzh.djiktzh.ch"
SEARCH_URL = f"{BASE_URL}/cgi-bin/nph-omniscgi.exe"
OUTPUT_HTML = "index.html"  # saved into the current folder (your PyCharm project)

# -------- Regex patterns (same as your script) --------
judge_block_pattern = r"(?:Verwaltungsrichter(?:in)?|Abteilungspräsident(?:in)?|Gerichtspräsident(?:in)?)[\s\S]+?(?=Gerichtsschreiber)"
clerk_pattern = r"Gerichtsschreiber(?:in)?\s+([A-ZÄÖÜ][^.]+)\."
decision_pattern = r"Geschäftsnummer:\s*([A-Z]{2}\.\d{4}\.\d{5})"
decision_date_pattern = r"vom\s+(.+?)\s+Spruchkörper"
section_pattern = r"Spruchkörper:\s*(.*?)(?=\s*/|\s*Weiterzug:|$)"
weight_pattern = r"Gewichtung:\s*([1-5])"
rechtsgebiet_pattern = r"Rechtsgebiet:\s*(.+?)\s*Betreff"
betreff_pattern = r", betreffend\s+(.+?),\s+hat sich ergeben"
length_pattern = r"hat sich ergeben:(.+?)(?=Demgemäss erkennt|Demgemäss verfügt|Demgemäss beschliesst|Der Einzelrichter erkennt|Der Einzelrichter verfügt|Die Einzelrichterin erkennt|Die Einzelrichterin verfügt)"
dispositiv_pattern = r"(Demgemäss erkennt|Demgemäss verfügt|Demgemäss beschliesst|Der Einzelrichter erkennt|Der Einzelrichter verfügt|Die Einzelrichterin erkennt|Die Einzelrichterin verfügt)(.+?)(?=Total der Kosten)"

def scrape_for_date(pub_date_ddmmyyyy: str):
    """Scrape one publication date; return a list of dict rows."""
    params = {
        "OmnisPlatform": "WINDOWS",
        "WebServerUrl": "",
        "WebServerScript": "/cgi-bin/nph-omniscgi.exe",
        "OmnisLibrary": "JURISWEB",
        "OmnisClass": "rtFindinfoWebHtmlService",
        "OmnisServer": "JURISWEB,127.0.0.1:7000",
        "Schema": "ZH_VG_WEB",
        "Parametername": "WWW",
        "Aufruf": "search",
        "cTemplate": "standard/results/resultpage.fiw",
        "cTemplateSuchkriterien": "standard/results/searchcriteriarow.fiw",
        "cTemplate_SuchstringValidateError": "standard/search.fiw",
        "cSprache": "GER",
        "cGeschaeftsart": "",
        "cGeschaeftsjahr": "",
        "cGeschaeftsnummer": "",
        "dEntscheiddatum": "",
        "bHasEntscheiddatumBis": "0",
        "dEntscheiddatumBis": "",
        "dPublikationsdatum": "",
        "bHasPublikationsdatumBis": "0",
        "dPublikationsdatumBis": "",
        "dErstPublikationsdatum": pub_date_ddmmyyyy,
        "bHasErstPublikationsdatumBis": "0",
        "dErstPublikationsdatumBis": "",
        "cSuchstringZiel": "F37_HTML",
        "cSuchstring": "",
        "nAnzahlTrefferProSeite": "50",
        "nSeite": "1"
    }

    resp = requests.get(SEARCH_URL, params=params, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = [BASE_URL + a["href"] for a in soup.find_all("a", href=True) if "F30_KEY" in a["href"]]

    rows = []
    for link in links:
        try:
            r = requests.get(link, timeout=10)
            r.encoding = "ISO-8859-1"  # important for umlauts
            s = BeautifulSoup(r.text, "html.parser")

            text = s.get_text("\n", strip=True)
            text = re.sub(r"\s+", " ", text)

            # Judges
            judges = None
            jb = re.search(judge_block_pattern, text)
            if jb:
                raw = jb.group(0)
                raw = re.sub(r"(Verwaltungsrichter(?:in)?|Abteilungspräsident(?:in)?|Gerichtspräsident(?:in)?)", "", raw)
                judges = [j.strip() for j in re.split(r",| und ", raw) if j.strip()]

            # Clerk
            cm = re.search(clerk_pattern, text)
            clerk = cm.group(1).strip() if cm else None

            # Decision number
            dm = re.search(decision_pattern, text)
            decision_number = dm.group(1).strip() if dm else None

            # Decision date
            ddm = re.search(decision_date_pattern, text)
            decision_date = ddm.group(1).strip() if ddm else None

            # Section
            sm = re.search(section_pattern, text)
            if sm and sm.group(1) and sm.group(1).strip():
                section = sm.group(1).strip()
            else:
                section = "Verwaltungskommission"

            # Weight
            wm = re.search(weight_pattern, text)
            weight = wm.group(1) if wm else None

            # Rechtsgebiet
            rgm = re.search(rechtsgebiet_pattern, text)
            rechtsgebiet = rgm.group(1).strip() if rgm else None

            # Betreff
            bm = re.search(betreff_pattern, text, flags=re.IGNORECASE | re.DOTALL)
            betreff = bm.group(1).strip() if bm else None

            # Length (words)
            lm = re.search(length_pattern, text, flags=re.DOTALL | re.IGNORECASE)
            decision_length = None
            if lm:
                decision_text = re.sub(r"\s+", " ", lm.group(1)).strip()
                decision_length = int(len(decision_text.split()))

            # Result
            disp = re.search(dispositiv_pattern, text, flags=re.IGNORECASE | re.DOTALL)
            result = None
            if disp:
                dtext = re.sub(r"\s+", " ", disp.group(2)).strip()
                if re.search(r"teilweise gutgeheissen|In teilweiser Gutheissung", dtext, re.IGNORECASE):
                    result = "Teilweise Gutheissung"
                elif re.search(r"gutgeheissen|In Gutheissung", dtext, re.IGNORECASE):
                    result = "Gutheissung"
                elif re.search(r"abgewiesen", dtext, re.IGNORECASE):
                    result = "Abweisung"
                elif re.search(r"gegenstandslos", dtext, re.IGNORECASE):
                    result = "Abschreibung als gegenstandslos"
                elif re.search(r"nicht eingetreten", dtext, re.IGNORECASE):
                    result = "Nichteintreten"

            # Dissenting Opinion Check
            dissenting_opinion = ""
            dissent_patterns = [
                r"Abweichende Meinung einer Kammerminderheit",
                r"Abweichende Meinung des Gerichtsschreibers",
                r"Abweichende Meinung der Gerichtsschreiberin",
                r"Abweichende Meinung einer Minderheit",
            ]

            for pattern in dissent_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    dissenting_opinion = "Ja!"
                    break

            rows.append({
                "Verfahrensnummer": decision_number,
                "Entscheiddatum": decision_date,
                "Abteilung": section,
                "Rechtsgebiet": rechtsgebiet,
                "Betreff": betreff,
                "Ausgang": result,
                "Gewichtung": weight,
                "Länge (Wörter)": decision_length,
                "Richter:innen": ", ".join(judges) if judges else None,
                "Gerichtsschreiber:in": clerk,
                "Minderheitsvotum": dissenting_opinion,
                "LinkURL": link,
            })
        except Exception as e:
            print(f"⚠️ Error with {link}: {e}")

    return rows

def build_html(days_data):
    """days_data = list of tuples (pub_date_str, rows:list[dict])"""
    tz = pytz.timezone("Europe/Zurich")
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M")
    parts = []
    parts.append("""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VG Zürich – Veröffentlichte Entscheide (letzte 7 Tage)</title>
<style>
  :root{--bg:#0b0f19;--panel:#111727;--muted:#9aa3b2;--text:#e8ecf1;--accent:#4da3ff;}
  body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Inter,Arial,sans-serif;background:var(--bg);color:var(--text);}
  header{padding:24px 16px;text-align:center;}
  h1{margin:0 0 8px 0;font-size:1.6rem;}
  .sub{color:var(--muted);font-size:.95rem}
  .wrap{max-width:1900px;margin:0 auto;padding:0 16px 56px}
  .day{background:var(--panel);border-radius:16px;padding:16px 16px 8px;margin:16px 0;box-shadow:0 10px 30px rgba(0,0,0,.25);display: block}
  .day h2{margin:4px 0 12px 0;font-size:1.2rem;color:#fff;display: block}
  .toolbar{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:8px 0 12px}
  table{width:100%;border-collapse:collapse;font-size:.95rem}
  th,td{padding:10px 8px;vertical-align:top;border-top:1px solid #1c2740}
  th{position:sticky;top:0;background:#121a2d;text-align:left}
  tr:hover{background:#0f1728}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#0e233a;color:#b9d8ff;border:1px solid #203a5c;font-size:.85rem}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  .empty{color:var(--muted);padding:8px 0}
  footer{color:var(--muted);text-align:center;padding:24px}
  /* Custom column widths */
  table td:nth-child(3), table th:nth-child(3) { width: 150px; } /* Abteilung column */
  table td:nth-child(9), table th:nth-child(9) { width: 300px; } /* Judges column */
  table td:nth-child(10), table th:nth-child(10) { width: 150px; } /* Clerk column */
</style>
<script>
function filterTable(dayId){
  const q = document.getElementById('q_'+dayId).value.toLowerCase();
  const rows = document.querySelectorAll('#tbl_'+dayId+' tbody tr');
  rows.forEach(tr=>{
    const text = tr.innerText.toLowerCase();
    tr.style.display = text.indexOf(q) !== -1 ? '' : 'none';
  });
}
</script>
</head>
<body>
<header>
  <h1>Veröffentlichte Entscheide – Verwaltungsgericht Zürich</h1>
  <div class="sub">Letzte 7 Publikationstage • Aktualisiert: """ + now + """</div>
</header>
<div class="wrap">
""")

    # Build a section per day
    for idx, (pub_date, rows) in enumerate(days_data, start=1):
        parts.append(f'<section class="day"><h2>Publikationen am {html.escape(pub_date)}</h2>')
        parts.append(f'<div class="toolbar">')
        if not rows:
            parts.append('<div class="empty">Keine Entscheide publiziert.</div></section>')
            continue

        parts.append(f'<table id="tbl_{idx}"><thead><tr>')
        headers = ["Verfahrensnummer","Entscheiddatum","Abteilung","Rechtsgebiet","Betreff","Ausgang","Gewichtung","Länge (Wörter)","Richter:innen","Gerichtsschreiber:in", "Minderheitsvotum", "Link"]
        for h in headers:
            parts.append(f"<th>{html.escape(h)}</th>")
        parts.append("</tr></thead><tbody>")

        for r in rows:
            parts.append("<tr>")
            parts.append(f"<td>{html.escape(r.get('Verfahrensnummer') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Entscheiddatum') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Abteilung') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Rechtsgebiet') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Betreff') or '')}</td>")
            parts.append(f"<td><span class='pill'>{html.escape(r.get('Ausgang') or '')}</span></td>")
            parts.append(f"<td>{html.escape(str(r.get('Gewichtung') or ''))}</td>")
            parts.append(f"<td>{html.escape(str(r.get('Länge (Wörter)') or ''))}</td>")
            parts.append(f"<td>{html.escape(r.get('Richter:innen') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Gerichtsschreiber:in') or '')}</td>")
            parts.append(f"<td>{html.escape(r.get('Minderheitsvotum') or '')}</td>")
            link = r.get("LinkURL")
            if link:
                parts.append(f'<td><a href="{html.escape(link)}" target="_blank">Link</a></td>')
            else:
                parts.append("<td></td>")
            parts.append("</tr>")
        parts.append("</tbody></table></section>")

    parts.append("""</div>
<footer>Die vorliegende Website ist ein privates Projekt und wird nicht vom Verwaltungsgericht Zürich geführt.</footer>
</body>
</html>""")

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return os.path.abspath(OUTPUT_HTML)

# ------------ Run: scrape last 7 publication days and build HTML ------------
if __name__ == "__main__":
    days = []
    for i in range(7):
        pub_date = (datetime.today() - timedelta(days=i)).strftime("%d.%m.%Y")
        rows = scrape_for_date(pub_date)
        days.append((pub_date, rows))

    out_path = build_html(days)
    print(f"✅ HTML erstellt: {out_path}")

OUTPUT_HTML = os.path.join(os.getcwd(), "index.html")











