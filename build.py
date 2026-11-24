#!/usr/bin/env python3
"""Genera la web de Historias Profesionales a partir del RSS de Spotify for Creators
y del feed de YouTube. Solo usa la librería estándar de Python.

Uso:
  python build.py                      # descarga RSS y YouTube, genera _site/
  python build.py --rss-file f.xml --yt-file y.xml   # usa archivos locales (pruebas)
"""
import argparse, datetime as dt, html, json, os, re, shutil, sys, urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
      "podcast": "https://podcastindex.org/namespace/1.0",
      "atom": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
esc = html.escape


# ---------------------------------------------------------------- datos
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (HistoriasProfesionales web build)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


class Sanitizer(HTMLParser):
    """Deja solo etiquetas seguras de la descripción del episodio."""
    OK = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "a"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.OK:
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("http://", "https://")):
                self.out.append(f'<a href="{esc(href)}" target="_blank" rel="noopener">')
            else:
                self.out.append("<a>")
        else:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in self.OK and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(esc(data))


def clean_html(s):
    p = Sanitizer()
    p.feed(s or "")
    out = "".join(p.out)
    out = re.sub(r"<p>\s*(<br>)?\s*</p>", "", out)
    return out


def text_of(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def split_title(title):
    """'Episodio #30 | Nombre - Rol (Empresa)' -> (30, 'Nombre', 'Rol (Empresa)')"""
    m = re.match(r"\s*Episodio\s*#?\s*(\d+)\s*[|\-–:]\s*(.*)", title, re.I)
    if not m:
        return None, title.strip(), ""
    num, rest = int(m.group(1)), m.group(2).strip()
    if " - " in rest:
        guest, role = rest.split(" - ", 1)
    else:
        guest, role = rest, ""
    return num, guest.strip(), role.strip()


NUM_RE = re.compile(r"(?:#\s?|\bEp\.?\s?|\bEpisodio\s)(\d+)\b", re.I)


def ep_num(title):
    """Número del episodio con cualquier formato de título: 'Episodio #30 | …', '… · Ep. 30', '… #30'."""
    n = split_title(title)[0]
    if n is None:
        m = NUM_RE.search(title or "")
        n = int(m.group(1)) if m else None
    return n


def spotify_url(link, transcript):
    """El RSS no trae el enlace de open.spotify.com, pero la URL de la transcripción lleva el ID del episodio:
    transcript-files.spotifycdn.com/<show>/<episodio>/transcript.srt"""
    m = re.search(r"spotifycdn\.com/[^/]+/([A-Za-z0-9]{22})/", transcript or "")
    return f"https://open.spotify.com/episode/{m.group(1)}" if m else link


def parse_rss(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ch = root.find("channel")
    img = ch.find("itunes:image", NS)
    show = {"image": img.get("href") if img is not None else ""}
    eps = []
    for it in ch.findall("item"):
        title = it.findtext("title", "")
        num, guest, role = split_title(title)
        if num is None:  # título nuevo (estilo SEO): número aquí, nombre y rol desde data/episodios.json
            num, guest, role = ep_num(title), "", ""
        enc = it.find("enclosure")
        im = it.find("itunes:image", NS)
        tr = it.find("podcast:transcript", NS)
        desc = it.findtext("description", "") or it.findtext("itunes:summary", "", NS)
        try:
            date = dt.datetime.strptime(it.findtext("pubDate", "")[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            date = None
        eps.append({
            "num": num, "title": title.strip(), "guest": guest, "role": role,
            "date": date, "duration": it.findtext("itunes:duration", "", NS),
            "image": im.get("href") if im is not None else show["image"],
            "audio": enc.get("url") if enc is not None else "",
            "spotify": spotify_url(it.findtext("link", ""), tr.get("url") if tr is not None else ""),
            "transcript": tr.get("url") if tr is not None else "",
            "desc_html": clean_html(desc), "summary": text_of(desc),
            "youtube": "",
        })
    return show, eps


def parse_youtube(xml_bytes):
    """Devuelve {num: {'id':..., 'title':..., 'date':...}} solo de episodios completos (no shorts)."""
    out = {}
    root = ET.fromstring(xml_bytes)
    for e in root.findall("atom:entry", NS):
        link = e.find("atom:link", NS)
        href = link.get("href") if link is not None else ""
        if "/shorts/" in href:
            continue
        title = e.findtext("atom:title", "", NS)
        num = ep_num(title)  # vale para "Episodio #30 | …" y "¿Cómo es ser…? | Nombre · Historias Profesionales Ep. 30"
        if num is None:
            continue
        out[str(num)] = {"id": e.findtext("yt:videoId", "", NS), "title": title,
                         "date": e.findtext("atom:published", "", NS)[:10]}
    return out


def fetch_apple():
    """Episodios en Apple Podcasts vía la API pública de iTunes."""
    data = json.loads(fetch(f"https://itunes.apple.com/lookup?id={CFG['apple_id']}&entity=podcastEpisode&limit=300&country=es"))
    out = {}
    for r in data.get("results", []):
        if r.get("wrapperType") != "podcastEpisode":
            continue
        num = ep_num(r.get("trackName", ""))
        if num is not None and r.get("trackId"):
            out[str(num)] = f"https://podcasts.apple.com/es/podcast/id{CFG['apple_id']}?i={r['trackId']}"
    return out


def fetch_ivoox():
    """Episodios en iVoox leyendo las páginas del pódcast."""
    out = {}
    for page in range(1, 8):
        html_ = fetch(CFG["ivoox_pages"].format(page)).decode("utf-8", "ignore")
        hits = re.findall(r"ivoox\.com/episodio-(\d+)-[a-z0-9-]*?_rf_(\d+)_1\.html", html_)
        hits += re.findall(r"ivoox\.com/[a-z0-9-]*?-ep-(\d+)_rf_(\d+)_1\.html", html_)
        if not hits:
            break
        for n, rf in hits:
            out.setdefault(n, f"https://go.ivoox.com/rf/{rf}")
    return out


# ---------------------------------------------------------------- formato
def fecha(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}" if d else ""


def fecha_corta(d):
    return f"{d.day} {MESES[d.month - 1][:3]} {d.year}" if d else ""


def duracion(s):
    parts = [int(x) for x in re.findall(r"\d+", s or "")]
    if not parts:
        return ""
    if len(parts) == 1:
        secs = parts[0]
    else:
        while len(parts) < 3:
            parts.insert(0, 0)
        secs = parts[0] * 3600 + parts[1] * 60 + parts[2]
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h} h {m} min" if h else f"{m} min"


def iso_dur(s):
    parts = [int(x) for x in re.findall(r"\d+", s or "")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return f"PT{parts[-3]}H{parts[-2]}M{parts[-1]}S"


ICONS = json.load(open(os.path.join(ROOT, "assets", "icons.json"), encoding="utf-8"))


def icon(name, cls="ic"):
    d = ICONS.get(name)
    if not d:
        return ""
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="{d}"/></svg>'




# ---------------------------------------------------------------- utilidades
def slugify(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)[:60].strip("-")


def norm_words(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]{3,}", s)


def role_base(role):
    return re.sub(r"\s*\(.*?\)", "", role or "").strip()


def srt_to_paragraphs(srt):
    """SRT -> lista de párrafos legibles."""
    lines = []
    for ln in srt.splitlines():
        ln = ln.strip()
        if not ln or ln.isdigit() or "-->" in ln:
            continue
        lines.append(ln)
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    sents = re.split(r"(?<=[.!?…])\s+", text)
    paras, cur = [], []
    for s in sents:
        cur.append(s)
        if len(" ".join(cur)) > 650:
            paras.append(" ".join(cur)); cur = []
    if cur:
        paras.append(" ".join(cur))
    return paras


LINK_LINE = re.compile(r"(https?://|lnkd\.in|Episodio \d+ en |Redes del Podcast|LinkedIn de )", re.I)


def desc_clean(desc_html, drop_topics=False):
    """Quita de la descripción las líneas de enlaces a plataformas (ya están en los botones)
    y, si se pide, los bullets con emoji (se muestran aparte como temas clave)."""
    out = []
    for p in re.findall(r"<p>.*?</p>|[^<]+|<(?!p>)[^>]*>", desc_html or "", re.S):
        if not p.startswith("<p>"):
            out.append(p); continue
        segs = re.split(r"(<br\s*/?>)", p[3:-4])
        keep = []
        for s in segs:
            if s.startswith("<br"):
                keep.append(s); continue
            t = text_of(s)
            if LINK_LINE.search(t):
                continue
            if drop_topics and (re.match(r"^[^\w\s¿¡\"'(«]{1,3}\s", t) and not t[:1].isascii()):
                continue
            if drop_topics and re.search(r"profundizamos en:?\s*$", t, re.I):
                continue
            keep.append(s)
        inner = re.sub(r"^(\s*<br\s*/?>\s*)+|(\s*<br\s*/?>\s*)+$", "", "".join(keep))
        inner = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", inner)
        if text_of(inner):
            out.append(f"<p>{inner}</p>")
    return "".join(out)


def topics_from(desc_html):
    """Los bullets con emoji de la descripción -> [(emoji, texto)]."""
    parts = re.split(r"<br\s*/?>|</p>|</li>", desc_html or "")
    out = []
    for p in parts:
        t = text_of(p)
        if len(t) < 25:
            continue
        m = re.match(r"^([^\w\s¿¡\"'(«]{1,3})\s*(.+)$", t)
        if m and not m.group(1).isascii() and not LINK_LINE.search(t):
            out.append((m.group(1), m.group(2)))
    return out[:6]


def summary_from(e):
    t = e["summary"]
    t = re.sub(r"^\W*¡?Episodio \d+[^!]*!\s*", "", t)
    if len(t) <= 300:
        return t
    cut = t[:300]
    i = max(cut.rfind(". "), cut.rfind("? "))
    return (cut[:i + 1] if i > 120 else cut.rsplit(" ", 1)[0] + "…")


# ---------------------------------------------------------------- plantilla base
def site_url():
    u = os.environ.get("SITE_URL") or CFG.get("site_url") or ""
    return (u.rstrip("/") + "/") if u else ""


def abs_url(path):
    s = site_url()
    return s + path if s else ""


def page(title, desc, body, rel="", og_image="", path="", extra_head="", ld=None, home=False):
    def nav_href(anchor):
        return f"#{anchor}" if home else f"{rel}index.html#{anchor}"
    nav = [("episodios", "Episodios"), ("preguntas", "Pregunta al invitado"), ("proponer", "Propón un invitado"),
           ("sobre", "Sobre el pódcast"), ("sobre-mi", "Sobre mí")]
    nav_html = "".join(f'<a href="{nav_href(a)}" data-sec="{a}">{t}</a>' for a, t in nav)
    socials = "".join(
        f'<a href="{esc(s["url"])}" target="_blank" rel="noopener" aria-label="{esc(s["name"])}">{icon(s["id"])}</a>'
        for s in CFG["socials"])
    year = dt.date.today().year
    canon = abs_url(path)
    og = og_image if og_image.startswith("http") or not site_url() else abs_url(og_image)
    if og and not og.startswith("http") and not site_url():
        og = rel + og
    lds = ""
    for item in (ld or []):
        lds += f'<script type="application/ld+json">{json.dumps(item, ensure_ascii=False)}</script>\n'
    stats = ""
    if CFG.get("goatcounter"):
        stats = f'<script data-goatcounter="https://{esc(CFG["goatcounter"])}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{f'<link rel="canonical" href="{esc(canon)}">' if canon else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(CFG['site_name'])}">
<meta property="og:locale" content="es_ES">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
{f'<meta property="og:url" content="{esc(canon)}">' if canon else ''}
<meta property="og:image" content="{esc(og)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#1F110A">
<link rel="icon" href="{rel}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{esc(CFG['site_name'])}" href="{esc(CFG['rss_url'])}">
<link rel="preload" href="{rel}assets/fonts/bowlby-one-sc.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{rel}assets/fonts/manrope.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{rel}assets/style.css">
{extra_head}{lds}{stats}
</head>
<body>
<a class="skip" href="#contenido">Saltar al contenido</a>
<header class="top">
  <div class="wrap top-in">
    <a class="brand" href="{rel}index.html" aria-label="Historias Profesionales, inicio"><img src="{rel}assets/logo.svg" alt="Historias Profesionales" width="150" height="75"></a>
    <button class="menu" aria-label="Abrir menú" aria-expanded="false" aria-controls="nav"><span></span><span></span></button>
    <nav class="nav" id="nav" aria-label="Principal">{nav_html}</nav>
  </div>
</header>
<main id="contenido">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <div>
      <img src="{rel}assets/logo.svg" alt="" width="170" height="85" class="foot-logo" loading="lazy">
      <p class="muted">{esc(CFG['tagline'])}. Presentado por {esc(CFG['host'])}.</p>
    </div>
    <div class="foot-cols">
      <div><h2 class="foot-h">Escúchalo</h2>{''.join(f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">{esc(p["name"])}</a>' for p in CFG['platforms'])}</div>
      <div><h2 class="foot-h">Síguelo</h2>{''.join(f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["name"])}</a>' for s in CFG['socials'] if s['id'] != 'youtube')}</div>
      <div><h2 class="foot-h">Temas</h2>{''.join(f'<a href="{rel}temas/{s["slug"]}/index.html">{esc(s["nombre"])}</a>' for s in CFG['sectores'])}</div>
      <div><h2 class="foot-h">Contacto</h2><a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a><a href="{nav_href('preguntas')}">Envía tu pregunta</a></div>
    </div>
  </div>
  <div class="wrap foot-base"><span>© {year} {esc(CFG['site_name'])} · <a href="{rel}privacidad/index.html">Privacidad</a> · <a href="{rel}aviso-legal/index.html">Aviso legal</a></span><span class="socials">{socials}</span></div>
</footer>
<script src="{rel}assets/app.js" defer></script>
</body>
</html>
"""


def platform_buttons():
    return "".join(
        f'<a class="pbtn pbtn-{p["id"]}" href="{esc(p["url"])}" target="_blank" rel="noopener">{icon(p["id"])}<span>{esc(p["name"])}</span></a>'
        for p in CFG["platforms"])


def ep_links(e):
    """Solo plataformas donde se conoce el enlace del episodio."""
    return [{"id": p["id"], "name": p["name"], "url": e["links"][p["id"]]}
            for p in CFG["platforms"] if e["links"].get(p["id"])]


def episode_buttons(e):
    return "".join(
        f'<a class="pbtn pbtn-{l["id"]}" href="{esc(l["url"])}" target="_blank" rel="noopener">{icon(l["id"])}<span>{esc(l["name"])}</span></a>'
        for l in ep_links(e))


def yt_thumb(vid):
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def lite_yt(e, rel=""):
    vid = e["youtube"]
    return (f'<button class="lite-yt" data-id="{vid}" aria-label="Ver el episodio {e["num"]} en vídeo">'
            f'<img src="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">'
            f'<span class="play">{icon("play")}</span></button>')


def fallback_attr(e):
    """Si la portada ligera no carga, usar la original de Spotify/YouTube."""
    if e["image_web"] != e["image"] and e["image"].startswith("http"):
        return f' onerror="this.onerror=null;this.src=\'{esc(e["image"])}\'"'
    return ""


def card(e, rel="", h="h3"):
    img = e["image_web"]
    meta = " · ".join(x for x in [fecha_corta(e["date"]), duracion(e["duration"])] if x)
    num = f"#{e['num']}" if e["num"] is not None else ""
    href = f"{rel}episodios/{e['slug']}/index.html"
    return f"""<article class="card reveal" data-search="{esc(e['search_short'])}" data-slug="{e['slug']}" data-sector="{e['sector']}">
  <a class="card-btn" href="{href}" data-ep="{e['slug']}" aria-label="{esc(e['title'])}">
    <span class="card-img"><img loading="lazy" src="{esc(img if img.startswith('http') else rel + img)}"{fallback_attr(e)} alt="" width="400" height="400"><span class="num">{num}</span><span class="card-play" aria-hidden="true">{icon("play")}</span></span>
    <span class="card-body">
      <{h} class="card-h">{esc(e['guest'])}</{h}>
      <span class="role">{esc(e['role'])}</span>
      <span class="muted small card-meta">{esc(meta)}</span>
    </span>
  </a>
</article>"""


def modal_html():
    return """
<div class="modal" id="modal" hidden>
  <div class="modal-bg" data-close></div>
  <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="m-guest">
    <button class="modal-x" data-close aria-label="Cerrar">×</button>
    <div class="m-head">
      <img id="m-img" src="" alt="">
      <div>
        <p class="m-num" id="m-num"></p>
        <h3 id="m-guest"></h3>
        <p class="role" id="m-role"></p>
        <p class="muted small" id="m-meta"></p>
      </div>
    </div>
    <p class="m-label">¿Dónde quieres escucharlo?</p>
    <div class="m-links" id="m-links"></div>
    <a class="m-more" id="m-more" href="#">Ver la página del episodio y la transcripción →</a>
  </div>
</div>"""


def ep_data_json(eps, rel=""):
    data = {}
    for e in eps:
        img = e["image_web"]
        data[e["slug"]] = {
            "num": f"#{e['num']}" if e["num"] is not None else "", "guest": e["guest"], "role": e["role"],
            "img": img if img.startswith("http") else rel + img,
            "meta": " · ".join(x for x in [fecha_corta(e["date"]), duracion(e["duration"])] if x),
            "links": ep_links(e), "page": f"{rel}episodios/{e['slug']}/index.html"}
    payload = {"eps": data, "icons": {p["id"]: icon(p["id"]) for p in CFG["platforms"]}}
    js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return '<script id="ep-data" type="application/json">' + js + '</script>'


# ---------------------------------------------------------------- secciones de la portada
def section_sobre():
    faq = CFG.get("faq") or []
    faq_html = ""
    if faq:
        faq_html = '<h3>Preguntas frecuentes</h3><div class="faq">' + "".join(
            f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq) + "</div>"
    return f"""
<section class="sec sobre" id="sobre">
  <div class="wrap narrow">
    <p class="eyebrow">Sobre el pódcast</p>
    <h2 class="sec-title">Detrás de cada persona hay una historia</h2>
    <div class="prose">
      <p class="lead">Historias Profesionales es un pódcast de entrevistas en el que profesionales de sectores muy distintos cuentan cómo llegaron a donde están: qué estudiaron, qué decisiones tomaron, cómo es de verdad su día a día y qué consejo darían a quien quiera dedicarse a lo mismo.</p>
      <h3>Quiénes vienen de invitados</h3>
      <p>Por aquí han pasado una azafata, un mago, una arquitecta, un periodista, ingenieros, médicos, consultores, emprendedores… La idea es ir más allá del cargo y la empresa y conocer a la persona: lo mejor y lo peor de su profesión, sus fracasos, sus referentes y las anécdotas que no salen en el currículum.</p>
      <h3>Qué te vas a llevar</h3>
      <p>Si estás eligiendo carrera, pensando en cambiar de trabajo o simplemente tienes curiosidad por cómo se ganan la vida otros, aquí vas a escuchar cómo es cada profesión por dentro, sin filtros.</p>
      <h3>Una tradición: el invitado propone a los siguientes</h3>
      <p>Al final de cada entrevista, el invitado propone a personas a las que le gustaría escuchar en el pódcast. No es una obligación ni todas acaban viniendo, pero muchas de las próximas historias llegan así.</p>
      <h3>Tú también formas parte</h3>
      <p>Las preguntas de la audiencia se hacen durante la grabación. Cuando anunciamos al próximo invitado, puedes <a href="#preguntas">enviar la tuya aquí</a>, también de forma anónima. Y si conoces a alguien con una historia que merece ser contada, <a href="#proponer">propónnoslo</a>.</p>
      <h3>Quién lo presenta</h3>
      <p>Lo presenta y produce {esc(CFG['host'])}. <a href="#sobre-mi">Más sobre mí</a>.</p>
      {faq_html}
    </div>
  </div>
  <div class="wrap">
    <div class="cta-in reveal">
      <div>
        <h2>¿Quieres participar o proponer a alguien?</h2>
        <p>Si tienes una historia profesional que contar, conoces a alguien que debería venir o quieres colaborar, escríbenos a <strong>{esc(CFG['email'])}</strong>.</p>
      </div>
      <div class="cta-btns">
        <a class="btn" href="mailto:{esc(CFG['email'])}?subject=Historias%20Profesionales">Escribir un correo</a>
        <a class="btn-ghost" href="#proponer">Proponer un invitado</a>
      </div>
    </div>
  </div>
</section>
"""


def section_sobre_mi():
    m = CFG["sobre_mi"]
    intro = "".join(f"<p>{esc(p)}</p>" for p in m["intro"])
    chips = "".join(f"<span>{esc(x)}</span>" for x in m["fuera"])
    return f"""
<section class="sec sobremi" id="sobre-mi">
  <div class="wrap sm-in">
   <div class="sm-text">
    <p class="eyebrow">Sobre mí</p>
    <h2 class="sec-title">{esc(m['nombre'])}</h2>
    <p class="sm-tag">{esc(m['titular'])}</p>
    <div class="prose sm-prose">{intro}</div>
    <p class="sm-label">{esc(m['fuera_titulo'])}</p>
    <div class="chips">{chips}</div>
    <p><a class="btn-ghost sm-li" href="{esc(m['linkedin'])}" target="_blank" rel="noopener">{icon('linkedin')} Conecta conmigo en LinkedIn</a></p>
   </div>
   <figure class="sm-foto"><img src="{esc(m['foto'])}" alt="{esc(CFG['host_full'])} grabando Historias Profesionales" loading="lazy" width="900" height="900"></figure>
  </div>
</section>
"""


def proximo_html():
    """Próximo invitado anunciado (config.json → proximo_invitado). Vacío = no se muestra."""
    p = CFG.get("proximo_invitado") or {}
    if not p.get("nombre"):
        return ""
    rol = f'<span class="next-rol">{esc(p["rol"])}</span>' if p.get("rol") else ""
    link = (f' <a href="{esc(p["enlace"])}" target="_blank" rel="noopener">Ver el anuncio</a>'
            if p.get("enlace") else "")
    return (f'<div class="next-guest"><span class="next-lab">Próximo invitado</span>'
            f'<strong>{esc(p["nombre"])}</strong>{rol}<span class="next-cta">¿Qué le preguntarías?{link}</span></div>')


def section_preguntas():
    P = CFG["preguntas"]
    f = P["campos"]
    abierto = bool((CFG.get("proximo_invitado") or {}).get("nombre"))
    if abierto:
        lado = f"""
      <div class="thanks" id="thanks" hidden role="status">
        <h3>¡Gracias!</h3>
        <p>Tu pregunta ha llegado. La revisamos y, si encaja, aparecerá aquí abajo y la escucharás en el episodio.</p>
      </div>
      <form class="form" id="qform" data-action="{esc(P['form_action'])}">
        <input type="hidden" name="{f['tipo']}" value="Pregunta">
        <label class="check anon"><input type="checkbox" id="anon"> Prefiero preguntar de forma anónima</label>
        <label id="name-label"><span>Tu nombre <span class="muted">(el que aparecerá en la web y diremos en el episodio)</span></span>
          <input type="text" id="nombre" name="{f['nombre']}" required maxlength="80" autocomplete="name">
        </label>
        <label>Tu pregunta
          <textarea name="{f['mensaje']}" required rows="5" maxlength="1500"></textarea>
        </label>
        <label class="check"><input type="checkbox" required> <span id="consent">Acepto que mi pregunta y mi nombre aparezcan en esta web y se lean en el pódcast.</span></label>
        <p class="muted small legal-note">Más información en la <a href="privacidad/index.html">política de privacidad</a>.</p>
        <button class="btn" type="submit" id="qsend">Enviar pregunta</button>
      </form>"""
        lead = "Deja tu pregunta y, si sale elegida, se la haremos durante la grabación y diremos tu nombre."
    else:
        lado = """
      <div class="form locked" role="status">
        <span class="lock-ico" aria-hidden="true">🔒</span>
        <h3>Aún no hemos anunciado al próximo invitado</h3>
        <p>En cuanto lo anunciemos en Instagram, podrás dejarle tu pregunta aquí. Mientras tanto, ¿conoces a alguien a quien te gustaría escuchar? <a href="#proponer">Propónnoslo</a>.</p>
        <a class="btn-ghost" href="https://www.instagram.com/historiasprofesionales/" target="_blank" rel="noopener">Seguir en Instagram</a>
      </div>"""
        lead = "Cada vez que anunciamos a un invitado, abrimos este espacio para que le dejes tu pregunta. Si sale elegida, se la hacemos durante la grabación y decimos tu nombre."
    return f"""
<section class="sec preguntas" id="preguntas">
  <div class="wrap preg-in">
    <div class="preg-text">
      <p class="eyebrow">Participa</p>
      <h2 class="sec-title">Pregunta al próximo invitado</h2>
      {proximo_html()}
      <p class="lead">{lead}</p>
      <p class="muted small">También recogemos preguntas en Instagram: <a href="https://www.instagram.com/historiasprofesionales/" target="_blank" rel="noopener">@historiasprofesionales</a>.</p>
    </div>
    <div>{lado}
    </div>
  </div>
  <div class="wrap" id="muro" data-csv="{esc(P['csv'])}" hidden>
    <div class="muro-head">
      <h3 class="sec-title muro-title">Lo que nos habéis preguntado</h3>
      <p class="muted small">Las preguntas se publican después de revisarlas.</p>
    </div>
    <div class="muro" id="muro-list"></div>
  </div>
</section>
"""


def section_proponer():
    P = CFG["preguntas"]
    f = P["campos"]
    return f"""
<section class="sec proponer" id="proponer">
  <div class="wrap preg-in">
    <div class="preg-text">
      <p class="eyebrow">Propón</p>
      <h2 class="sec-title">¿A quién te gustaría escuchar?</h2>
      <p class="lead">¿Conoces a alguien con una profesión curiosa o una trayectoria que merece ser contada? Cuéntanos quién es y cómo podemos contactar con esa persona.</p>
      <p class="muted small">Las propuestas no se publican: solo las usamos para valorarlas y, si encajan, escribir a la persona propuesta. También puedes escribirnos a <a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a>.</p>
    </div>
    <div>
      <div class="thanks" id="pthanks" hidden role="status">
        <h3>¡Gracias!</h3>
        <p>Tu propuesta ha llegado. La revisamos y, si encaja, nos pondremos en contacto con esa persona.</p>
      </div>
      <form class="form" id="pform" data-action="{esc(P['form_action'])}">
        <input type="hidden" name="{f['tipo']}" value="Propuesta de invitado">
        <input type="hidden" name="{f['mensaje']}" id="pmsg">
        <label>¿A quién propones? <input type="text" id="p-quien" required maxlength="120" placeholder="Nombre y apellidos"></label>
        <label>¿A qué se dedica? <input type="text" id="p-rol" required maxlength="160" placeholder="Profesión, cargo o empresa"></label>
        <label><span>¿Cómo podemos contactarle? <span class="muted">(LinkedIn, Instagram, correo…)</span></span>
          <input type="text" id="p-contacto" required maxlength="200" placeholder="Enlace o usuario">
        </label>
        <label>¿Por qué sería un buen invitado?
          <textarea id="p-porque" rows="4" maxlength="1200" placeholder="Qué hace de especial su historia o su profesión"></textarea>
        </label>
        <label><span>Tu nombre <span class="muted">(no se publica)</span></span>
          <input type="text" name="{f['nombre']}" required maxlength="80" autocomplete="name">
        </label>
        <label><span>Tu correo <span class="muted">(opcional, por si necesitamos más datos)</span></span>
          <input type="text" id="p-mail" maxlength="120" autocomplete="email">
        </label>
        <label class="check"><input type="checkbox" required> <span>Confirmo que el contacto que facilito es público o que la persona propuesta está de acuerdo, y acepto que usemos estos datos solo para valorar la propuesta y contactar con ella.</span></label>
        <p class="muted small legal-note">Más información en la <a href="privacidad/index.html">política de privacidad</a>.</p>
        <button class="btn" type="submit" id="psend">Enviar propuesta</button>
      </form>
    </div>
  </div>
</section>
"""


def podcast_ld(show):
    ld = {"@context": "https://schema.org", "@type": "PodcastSeries", "name": CFG["site_name"],
          "description": CFG["description"], "image": show["image"], "inLanguage": "es", "webFeed": CFG["rss_url"],
          "author": {"@type": "Person", "name": CFG["host_full"], "url": CFG["sobre_mi"]["linkedin"]},
          "sameAs": [p["url"] for p in CFG["platforms"]] + [s["url"] for s in CFG["socials"]]}
    if site_url():
        ld["url"] = site_url()
    return ld


def episode_ld(e, show):
    ld = {"@context": "https://schema.org", "@type": "PodcastEpisode",
          "name": e["title"], "episodeNumber": e["num"], "description": e["meta_desc"],
          "partOfSeries": {"@type": "PodcastSeries", "name": CFG["site_name"], "url": site_url() or None},
          "image": e["image"], "inLanguage": "es",
          "author": {"@type": "Person", "name": CFG["host_full"]},
          "actor": [{"@type": "Person", "name": e["guest"], "jobTitle": e["role"]}]}
    if e["date"]:
        ld["datePublished"] = e["date"].strftime("%Y-%m-%d")
    if e["duration"]:
        ld["timeRequired"] = iso_dur(e["duration"])
    if e["audio"]:
        ld["associatedMedia"] = {"@type": "MediaObject", "contentUrl": e["audio"]}
    if e["youtube"]:
        ld["video"] = {"@type": "VideoObject", "name": e["title"], "description": e["meta_desc"],
                       "thumbnailUrl": yt_thumb(e["youtube"]), "embedUrl": f"https://www.youtube.com/embed/{e['youtube']}",
                       "uploadDate": e["date"].strftime("%Y-%m-%d") if e["date"] else None}
    if site_url():
        ld["url"] = abs_url(f"episodios/{e['slug']}/")
    return ld


def build_index(show, eps):
    latest = eps[0]
    count = len([e for e in eps if e["num"]])
    media = lite_yt(latest) if latest["youtube"] else f'<img class="cover" src="{esc(latest["image"])}" alt="">'
    if latest["youtube"]:
        media = media.replace('loading="lazy" width="480" height="360"', 'fetchpriority="high" width="1280" height="720"').replace("hqdefault", "maxresdefault")
    desc = desc_clean(latest["desc_html"]) or f'<p>{esc(latest["summary"])}</p>'
    num_label = f"Episodio #{latest['num']}" if latest["num"] is not None else ""
    used = [s for s in CFG["sectores"] if any(e["sector"] == s["slug"] for e in eps)]
    chips = '<button class="fchip on" data-f="">Todos</button>' + "".join(
        f'<button class="fchip" data-f="{s["slug"]}">{esc(s["corto"])}</button>' for s in used)
    temas = " · ".join(f'<a href="temas/{s["slug"]}/index.html">{esc(s["nombre"])}</a>' for s in used)
    faq = CFG.get("faq") or []
    lds = [podcast_ld(show)]
    if faq:
        lds.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    body = f"""
<section class="hero" id="inicio">
  <div class="wrap hero-in">
    <div class="hero-text">
      <h1>Último episodio</h1>
      <p class="hero-guest"><span class="hero-num">{esc(num_label)}</span> <a href="episodios/{latest['slug']}/index.html">{esc(latest['guest'])}</a></p>
      <p class="hero-role">{esc(latest['role'])} · {esc(fecha(latest['date']))}</p>
      <div class="pbtns">{episode_buttons(latest)}</div>
    </div>
    <div class="hero-media">{media}</div>
  </div>
  <div class="wrap">
    <details class="ep-desc">
      <summary>De qué hablamos en este episodio</summary>
      <div class="ep-desc-body">{desc}<p><a href="episodios/{latest['slug']}/index.html">Ver la página del episodio y la transcripción →</a></p></div>
    </details>
  </div>
</section>

<section class="strip">
  <div class="wrap strip-in">
    <p><strong>Todo lo que no cabe en un currículum.</strong> {count} historias de profesionales de sectores muy distintos: ingeniería, salud, periodismo, finanzas, arte, deporte…</p>
    <a class="btn-ghost" href="#sobre">Qué es Historias Profesionales</a>
  </div>
</section>

<section class="sec episodes" id="episodios">
  <div class="wrap">
    <div class="sec-head">
      <div><h2 class="sec-title">Todos los episodios</h2><p class="sec-sub">Lo que nadie te cuenta de cada profesión</p></div>
      <label class="search">{icon('search')}<input id="q" type="search" placeholder="Busca una profesión, empresa o tema" aria-label="Buscar episodios"></label>
    </div>
    <div class="fchips" role="group" aria-label="Filtrar por tema">{chips}</div>
    <div class="grid collapsed" id="grid">
{''.join(card(e) for e in eps)}
    </div>
    <p class="empty muted" id="empty" hidden>No hay episodios con esa búsqueda.</p>
    <p class="muted small" id="deep" hidden>También buscamos dentro de lo que se dice en cada episodio.</p>
    <div class="more"><button class="btn-ghost" id="more" type="button">Ver todos los episodios ({len(eps)})</button></div>
    <p class="temas-links muted small">Explora por temas: {temas}</p>
  </div>
</section>
{section_preguntas()}
{section_proponer()}
{section_sobre()}
{section_sobre_mi()}
{modal_html()}
{ep_data_json(eps)}
"""
    title = f"{CFG['site_name']} · Todo lo que no cabe en un currículum"
    return page(title, CFG["description"], body, "", "assets/og/portada.jpg", "", "", lds, home=True)


# ---------------------------------------------------------------- página de episodio
def build_episode(e, eps, show):
    rel = "../../"
    others = [x for x in eps if x is not e and x["num"] is not None]
    rel_eps = [x for x in others if x["sector"] == e["sector"]][:3]
    if len(rel_eps) < 3:
        rel_eps += [x for x in others if x not in rel_eps][:3 - len(rel_eps)]
    idx = eps.index(e)
    prev_e = eps[idx + 1] if idx + 1 < len(eps) else None
    next_e = eps[idx - 1] if idx > 0 else None
    sector = next((s for s in CFG["sectores"] if s["slug"] == e["sector"]), None)
    media = lite_yt(e, rel) if e["youtube"] else f'<img class="cover" src="{esc(e["image_web"] if e["image_web"].startswith("http") else rel + e["image_web"])}"{fallback_attr(e)} alt="">'
    topics = "".join(f'<li><span class="t-emoji" aria-hidden="true">{esc(em)}</span><span>{esc(t)}</span></li>' for em, t in e["topics"])
    topics_html = f'<h2>Temas clave</h2><ul class="topics">{topics}</ul>' if topics else ""
    tr = e["transcript_paras"]
    tr_html = ""
    if tr:
        tr_html = f"""<details class="transcript" id="transcripcion">
  <summary><h2>Transcripción del episodio</h2><span class="muted small">Generada automáticamente · {sum(len(p.split()) for p in tr):,} palabras</span></summary>
  <div class="tr-body">{''.join(f'<p>{esc(p)}</p>' for p in tr)}</div>
</details>""".replace(",", ".")
    nav = ""
    if prev_e or next_e:
        nav = '<nav class="ep-nav" aria-label="Episodios cercanos">' + \
              (f'<a href="{rel}episodios/{prev_e["slug"]}/index.html">← #{prev_e["num"]} {esc(prev_e["guest"])}</a>' if prev_e else '<span></span>') + \
              (f'<a href="{rel}episodios/{next_e["slug"]}/index.html">#{next_e["num"]} {esc(next_e["guest"])} →</a>' if next_e else '<span></span>') + '</nav>'
    crumbs = f'<nav class="crumbs" aria-label="Migas de pan"><a href="{rel}index.html">Inicio</a> › <a href="{rel}index.html#episodios">Episodios</a>' + \
             (f' › <a href="{rel}temas/{sector["slug"]}/index.html">{esc(sector["nombre"])}</a>' if sector else "") + f' › <span>#{e["num"]}</span></nav>'
    meta = " · ".join(x for x in [fecha(e["date"]), duracion(e["duration"])] if x)
    body = f"""
<article class="ep-page">
  <div class="wrap">
    {crumbs}
    <div class="ep-top">
      <div class="ep-info">
        <p class="eyebrow">Episodio #{e['num']}</p>
        <h1 class="ep-h1">{esc(e['guest'])}</h1>
        <p class="hero-role">{esc(e['role'])}</p>
        <p class="muted small">{esc(meta)}</p>
        <p class="m-label">Escúchalo en</p>
        <div class="pbtns">{episode_buttons(e)}</div>
      </div>
      <div class="ep-media">{media}</div>
    </div>
    <div class="ep-cols">
      <div class="ep-main prose">
        <h2>De qué hablamos</h2>
        <div class="ep-desc-body">{desc_clean(e['desc_html'], bool(e['topics'])) or f"<p>{esc(e['summary'])}</p>"}</div>
        {topics_html}
        {tr_html}
      </div>
      <aside class="ep-side">
        <div class="side-box">
          <p class="m-label">¿Qué le preguntarías al próximo invitado?</p>
          <a class="btn" href="{rel}index.html#preguntas">Enviar mi pregunta</a>
        </div>
      </aside>
    </div>
    <section class="related">
      <h2 class="sec-title">Si te ha gustado, escucha también</h2>
      <div class="grid">{''.join(card(x, rel, "h3") for x in rel_eps)}</div>
    </section>
    {nav}
  </div>
</article>
{modal_html()}
{ep_data_json(rel_eps, rel)}
"""
    title = f"{e['guest']}, {role_base(e['role']) or 'invitado'} · Episodio #{e['num']} | {CFG['site_name']}"
    return page(title, e["meta_desc"], body, rel, e["og"], f"episodios/{e['slug']}/", "", [episode_ld(e, show), {
        "@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Inicio", "item": site_url() or None},
            {"@type": "ListItem", "position": 2, "name": f"Episodio #{e['num']}", "item": abs_url(f'episodios/{e["slug"]}/') or None}]}])


# ---------------------------------------------------------------- páginas de tema
def build_sector(s, eps, show):
    rel = "../../"
    lst = [e for e in eps if e["sector"] == s["slug"]]
    body = f"""
<section class="page-head"><div class="wrap">
  <nav class="crumbs" aria-label="Migas de pan"><a href="{rel}index.html">Inicio</a> › <a href="{rel}index.html#episodios">Episodios</a> › <span>{esc(s['nombre'])}</span></nav>
  <p class="eyebrow">Tema</p>
  <h1 class="page-h1">{esc(s['nombre'])}</h1>
  <p class="lead">{esc(s['intro'])}</p>
</div></section>
<section class="sec"><div class="wrap">
  <div class="grid">{''.join(card(e, rel, "h2") for e in lst)}</div>
  <p class="temas-links muted small">Otros temas: {" · ".join(f'<a href="{rel}temas/{x["slug"]}/index.html">{esc(x["nombre"])}</a>' for x in CFG["sectores"] if x is not s)}</p>
</div></section>
{modal_html()}
{ep_data_json(lst, rel)}
"""
    title = f"{s['nombre']}: entrevistas a profesionales | {CFG['site_name']}"
    desc = f"{s['intro']} {len(lst)} episodios de Historias Profesionales."
    return page(title, desc, body, rel, "assets/og/portada.jpg", f"temas/{s['slug']}/", "", [{
        "@context": "https://schema.org", "@type": "CollectionPage", "name": s["nombre"], "description": s["intro"]}])


# ---------------------------------------------------------------- legales y 404
def build_legal(kind):
    rel = "../"
    L = CFG["legal"]
    if kind == "privacidad":
        h1 = "Política de privacidad"
        content = f"""
<p><strong>Responsable:</strong> {esc(L['titular'])}. Contacto: <a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a>.</p>
<h2>Qué datos recogemos y para qué</h2>
<p>Solo a través de los formularios de esta web.</p>
<p><strong>«Pregunta al próximo invitado»:</strong> tu nombre (o «Anónimo» si eliges preguntar de forma anónima) y tu pregunta. Los usamos para leer tu pregunta, para hacerla durante la grabación del pódcast y, si la aprobamos, para publicarla en esta web junto a tu nombre (o como «Anónimo») y la fecha.</p>
<p><strong>«Propón un invitado»:</strong> tu nombre, tu correo si decides darlo y los datos de la persona que propones (nombre, a qué se dedica, un contacto y por qué la propones). Los usamos solo para valorar la propuesta y, si encaja, escribir a esa persona para invitarla. Las propuestas nunca se publican. Te pedimos que facilites solo un contacto público (por ejemplo, su perfil de LinkedIn o de Instagram) o uno que la persona propuesta haya aceptado compartir. Si eres la persona propuesta y no quieres que usemos tus datos, escríbenos y los borraremos.</p>
<h2>Base legal</h2>
<p>Tu consentimiento, que das al marcar la casilla del formulario. Puedes retirarlo cuando quieras escribiendo al correo de contacto.</p>
<h2>Dónde se guardan y quién los trata</h2>
<p>Los mensajes se guardan en Google Forms y Google Sheets (Google Ireland Ltd.), que actúa como encargado del tratamiento. Google puede tratar datos fuera del Espacio Económico Europeo con las garantías previstas en el RGPD (Marco de Privacidad de Datos UE-EE. UU. y cláusulas contractuales tipo). No cedemos tus datos a nadie más.</p>
<h2>Cuánto tiempo</h2>
<p>Hasta que pidas que los borremos o, como máximo, dos años desde el envío. Las preguntas que ya se hayan emitido en un episodio pueden seguir formando parte de esa grabación.</p>
<h2>Tus derechos</h2>
<p>Puedes pedir acceso, rectificación, supresión, oposición, limitación o portabilidad de tus datos escribiendo a <a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a>. Si crees que no los hemos tratado bien, puedes reclamar ante la Agencia Española de Protección de Datos (aepd.es).</p>
<h2>Cookies y servicios externos</h2>
<p>Esta web no usa cookies propias ni de publicidad. El vídeo de YouTube solo se carga si pulsas para verlo, y lo hace en modo de privacidad mejorada (youtube-nocookie.com). Los botones a Spotify, Apple Podcasts, Amazon Music, iVoox y redes sociales te llevan a esas plataformas, que tienen sus propias políticas.{' Para saber cuántas visitas recibe la web usamos GoatCounter, que no usa cookies ni guarda datos personales.' if CFG.get('goatcounter') else ''}</p>
"""
    else:
        h1 = "Aviso legal"
        content = f"""
<p><strong>Titular:</strong> {esc(L['titular'])}. Contacto: <a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a>.</p>
<p>Historias Profesionales es un proyecto personal sin ánimo de lucro: un pódcast de entrevistas sobre trayectorias profesionales. Esta web sirve para escuchar los episodios en las distintas plataformas y para enviar preguntas a los próximos invitados.</p>
<h2>Contenidos</h2>
<p>Las opiniones que expresan los invitados son suyas y no representan necesariamente a las empresas u organizaciones en las que trabajan. El logotipo, los textos y el diseño de la web pertenecen a Historias Profesionales. Las imágenes de los episodios y los nombres de marcas, empresas y plataformas pertenecen a sus respectivos titulares.</p>
<h2>Enlaces</h2>
<p>La web enlaza a plataformas externas (Spotify, YouTube, Apple Podcasts, Amazon Music, iVoox y redes sociales). No somos responsables de sus contenidos ni de sus políticas.</p>
<h2>Preguntas del público</h2>
<p>Las preguntas que se publican en la web se revisan antes. Nos reservamos el derecho a no publicar mensajes ofensivos, publicitarios o que incluyan datos de terceros.</p>
"""
    body = f"""
<section class="page-head"><div class="wrap narrow">
  <h1 class="page-h1">{h1}</h1>
</div></section>
<section class="sec legal"><div class="wrap narrow prose">{content}<p class="muted small">Última actualización: {fecha(dt.datetime.now())}.</p></div></section>
"""
    return page(f"{h1} | {CFG['site_name']}", f"{h1} de {CFG['site_name']}.", body, rel, "assets/og/portada.jpg", f"{kind}/")


def build_404():
    base = site_url()
    rel = base if base else ""
    body = f"""
<section class="page-head center nf"><div class="wrap narrow">
  <p class="eyebrow">Error 404</p>
  <h1 class="page-h1">Esta historia no está aquí</h1>
  <p class="lead">La página que buscas no existe o ha cambiado de sitio. Pero hay {CFG.get('_count', 30)} historias que sí.</p>
  <p><a class="btn" href="{rel}index.html#episodios">Ver los episodios</a></p>
</div></section>"""
    return page(f"Página no encontrada | {CFG['site_name']}", "Página no encontrada.", body, rel, "assets/og/portada.jpg").replace(
        '<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="description"')


def favicon():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1F110A"/>'
            '<path d="M12 50h12V40h12V30h12V20h6" fill="none" stroke="#E07A4A" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            '<circle cx="54" cy="13" r="5" fill="#F3EBDD"/></svg>')


# ---------------------------------------------------------------- imágenes (si hay Pillow)
def make_images(eps, offline):
    """Portadas ligeras (webp 400px) e imágenes para compartir (1200x630). Si no hay Pillow, se usan las remotas."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Aviso: sin Pillow, no se generan imágenes optimizadas", file=sys.stderr)
        return
    import io
    fonts = os.path.join(ROOT, "assets", "fonts")
    F = lambda name, size: ImageFont.truetype(os.path.join(fonts, name), size)
    og_dir = os.path.join(OUT, "assets", "og"); os.makedirs(og_dir, exist_ok=True)
    pw_dir = os.path.join(OUT, "assets", "portadas-web"); os.makedirs(pw_dir, exist_ok=True)
    base = Image.open(os.path.join(ROOT, "assets", "og-base.png")).convert("RGB")

    def wrap(draw, text, font, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= width:
                cur = t
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    def og(name, eyebrow, big, small, cover=None):
        im = base.copy(); d = ImageDraw.Draw(im)
        x, maxw = 80, (640 if cover else 1040)
        if cover is not None:
            c = cover.resize((420, 420)); mask = Image.new("L", (420, 420), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 420, 420), 28, fill=255)
            im.paste(c, (700, 130), mask)
        d.text((x, 248), eyebrow, font=F("manrope-ttf.ttf", 34), fill="#E07A4A")
        fb = F("bowlby.ttf", 66 if len(big) < 22 else 54)
        y = 298
        for ln in wrap(d, big.upper(), fb, maxw)[:2]:
            d.text((x, y), ln, font=fb, fill="#F3EBDD"); y += int(fb.size * 1.15)
        fs = F("manrope-ttf.ttf", 30)
        for ln in wrap(d, small, fs, maxw)[:3]:
            d.text((x, y + 14), ln, font=fs, fill="#C9BBA6"); y += 40
        im.save(os.path.join(og_dir, name), quality=85, optimize=True)

    # Portada: logo oficial centrado, para que se vea entero también en el recorte cuadrado de WhatsApp
    logo_path = os.path.join(ROOT, "assets", "logo-oficial.png")
    if os.path.exists(logo_path):
        im = Image.new("RGB", (1200, 630), (31, 16, 11))
        lg = Image.open(logo_path).convert("RGB")
        w = 560; h = int(lg.height * w / lg.width)
        im.paste(lg.resize((w, h), Image.LANCZOS), ((1200 - w) // 2, (630 - h) // 2))
        im.save(os.path.join(og_dir, "portada.jpg"), quality=88, optimize=True)
    else:
        og("portada.jpg", "PÓDCAST DE ENTREVISTAS", "Historias Profesionales", "Todo lo que no cabe en un currículum.")
    for e in eps:
        cover = None
        src = e["image"]
        local = None
        if e["num"] is not None and os.path.exists(os.path.join(ROOT, "assets", "portadas", f"{e['num']}.jpg")):
            local = os.path.join(ROOT, "assets", "portadas", f"{e['num']}.jpg")
        try:
            if local:
                cover = Image.open(local).convert("RGB")
            elif not offline and src.startswith("http"):
                cover = Image.open(io.BytesIO(fetch(src))).convert("RGB")
        except Exception as ex:
            print("Aviso: portada", e["num"], ex, file=sys.stderr)
        if cover is not None:
            w, h = cover.size; s = min(w, h)
            cover = cover.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
            cover.resize((400, 400), Image.LANCZOS).save(os.path.join(pw_dir, f"{e['slug']}.webp"), quality=80)
            e["image_web"] = f"assets/portadas-web/{e['slug']}.webp"
        og(f"{e['slug']}.jpg", f"EPISODIO #{e['num']}", e["guest"], e["role"], cover)
        e["og"] = f"assets/og/{e['slug']}.jpg"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rss-file")
    ap.add_argument("--yt-file")
    a = ap.parse_args()
    offline = bool(a.rss_file)

    rss = open(a.rss_file, "rb").read() if a.rss_file else fetch(CFG["rss_url"])
    show, eps = parse_rss(rss)
    if len(eps) < 5:
        sys.exit("ERROR: el RSS trae muy pocos episodios; no se publica para no romper la web.")

    # Nombre y rol de cada episodio, guardados para no depender del formato del título en Spotify
    epi_path = os.path.join(ROOT, "data", "episodios.json")
    epi = json.load(open(epi_path, encoding="utf-8")) if os.path.exists(epi_path) else {}
    for e in eps:
        k = str(e["num"])
        if e["num"] is None:
            continue
        if e["guest"]:
            epi[k] = {"invitado": e["guest"], "rol": e["role"]}
        elif k in epi:
            e["title_plataforma"] = e["title"]
            e["guest"], e["role"] = epi[k]["invitado"], epi[k]["rol"]
            e["title"] = f"Episodio #{e['num']} | {e['guest']}" + (f" - {e['role']}" if e["role"] else "")
        else:
            print(f"Aviso: el episodio {k} no tiene nombre de invitado; añádelo en data/episodios.json", file=sys.stderr)
    if not offline:
        json.dump(dict(sorted(epi.items(), key=lambda kv: -int(kv[0]))), open(epi_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    # Vídeos de YouTube (el feed solo trae los 15 últimos; se guardan en data/youtube.json)
    cache_path = os.path.join(ROOT, "data", "youtube.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    try:
        yt = open(a.yt_file, "rb").read() if a.yt_file else fetch(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={CFG['youtube_channel_id']}")
        for k, v in parse_youtube(yt).items():
            old = cache.get(k, {})
            if split_title(v["title"])[0] is None and old.get("title"):
                v["title"] = old["title"]  # conservar "Episodio #N | Nombre - Rol" si el título de YouTube cambia de formato
            cache[k] = {**old, **v}
    except Exception as ex:
        print("Aviso: no se pudo leer YouTube:", ex, file=sys.stderr)
    if not offline:
        json.dump(dict(sorted(cache.items(), key=lambda kv: -int(kv[0]))), open(cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    # Enlaces por plataforma
    links_path = os.path.join(ROOT, "data", "enlaces.json")
    links = json.load(open(links_path, encoding="utf-8")) if os.path.exists(links_path) else {}
    if not offline:
        for pid, fn in (("applepodcasts", fetch_apple), ("ivoox", fetch_ivoox)):
            try:
                links.setdefault(pid, {}).update(fn())
            except Exception as ex:
                print(f"Aviso: no se pudo leer {pid}:", ex, file=sys.stderr)
        json.dump(links, open(links_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    nums = set()
    for e in eps:
        if e["num"] is not None and str(e["num"]) in cache:
            e["youtube"] = cache[str(e["num"])]["id"]
        nums.add(e["num"])
    for k, v in cache.items():  # episodios que están en YouTube pero no en el RSS
        if int(k) not in nums and v.get("title", "").count("|"):
            n, g, r = split_title(v["title"])
            d = dt.datetime.strptime(v["date"], "%Y-%m-%d") if v.get("date") else None
            eps.append({"num": n, "title": v["title"], "guest": g, "role": r, "date": d, "duration": "",
                        "image": yt_thumb(v["id"]), "audio": "", "spotify": "", "transcript": "",
                        "desc_html": "", "summary": "", "youtube": v["id"]})
    desc_dir = os.path.join(ROOT, "data", "descripciones")  # descripción manual mientras el RSS no la trae
    for e in eps:
        f = os.path.join(desc_dir, f"{e['num']}.html")
        if not e.get("desc_html") and os.path.exists(f):
            raw = open(f, encoding="utf-8").read()
            e["desc_html"], e["summary"] = clean_html(raw), text_of(raw)
    eps.sort(key=lambda e: (e["num"] if e["num"] is not None else -1, e["date"] or dt.datetime.min), reverse=True)
    eps = [e for e in eps if e["num"] != 0] + [e for e in eps if e["num"] == 0]

    sect_path = os.path.join(ROOT, "data", "sectores.json")
    sect_map = json.load(open(sect_path, encoding="utf-8")) if os.path.exists(sect_path) else {}
    tr_dir = os.path.join(ROOT, "fixtures" if offline else "data", "transcripciones")
    os.makedirs(tr_dir, exist_ok=True)
    for e in eps:
        k = str(e["num"])
        e["links"] = {}
        if e["youtube"]:
            e["links"]["youtube"] = f"https://www.youtube.com/watch?v={e['youtube']}"
        if "open.spotify.com/episode/" in (e["spotify"] or ""):
            e["links"]["spotify"] = e["spotify"]
        for pid in ("spotify", "applepodcasts", "amazonmusic", "ivoox"):
            if pid not in e["links"] and k in links.get(pid, {}):
                e["links"][pid] = links[pid][k]
        if "spotify" not in e["links"] and e["spotify"]:
            e["links"]["spotify"] = e["spotify"]
        e["slug"] = "0-presentacion" if e["num"] == 0 else f"{e['num']}-{slugify(e['guest'])}"
        if e["num"] is not None and os.path.exists(os.path.join(ROOT, "assets", "portadas", f"{e['num']}.jpg")):
            e["image"] = f"assets/portadas/{e['num']}.jpg"
        e["image_web"] = e["image"]
        e["og"] = "assets/og/portada.jpg"
        # Tema
        sec = sect_map.get(k)
        if not sec:
            low = (e["role"] + " " + e["guest"]).lower()
            sec = next((s["slug"] for s in CFG["sectores"] if any(w in low for w in s.get("claves", []))), "otros")
        e["sector"] = sec if e["num"] != 0 else ""
        # Transcripción (se guarda en data/transcripciones para no descargarla cada vez)
        tpath = os.path.join(tr_dir, f"{k}.txt")
        paras = []
        if os.path.exists(tpath):
            paras = [p for p in open(tpath, encoding="utf-8").read().split("\n\n") if p.strip()]
        elif e["transcript"] and not offline:
            try:
                paras = srt_to_paragraphs(fetch(e["transcript"]).decode("utf-8", "ignore"))
                open(tpath, "w", encoding="utf-8").write("\n\n".join(paras))
            except Exception as ex:
                print("Aviso: transcripción", k, ex, file=sys.stderr)
        e["transcript_paras"] = paras
        e["topics"] = topics_from(e["desc_html"])
        role = role_base(e["role"])
        e["meta_desc"] = (f"{e['guest']} ({role}) cuenta su trayectoria en el episodio #{e['num']} de Historias Profesionales. "
                          + summary_from(e))[:300] if e["num"] else CFG["description"]
        e["search_short"] = " ".join(norm_words(f"{e['guest']} {e['role']} {e['summary'][:400]}"))

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"),
                    ignore=shutil.ignore_patterns("icons.json", "og-base.png", "*.ttf", "portadas"))
    if os.path.isdir(os.path.join(ROOT, "assets", "portadas")):
        shutil.copytree(os.path.join(ROOT, "assets", "portadas"), os.path.join(OUT, "assets", "portadas"))
    open(os.path.join(OUT, "assets", "favicon.svg"), "w").write(favicon())
    make_images(eps, offline)
    CFG["_count"] = len([e for e in eps if e["num"]])

    # Índice de búsqueda completo (incluye transcripciones), se carga solo al buscar
    idx = {e["slug"]: " ".join(sorted(set(norm_words(" ".join([e["title"], e["summary"]] + e["transcript_paras"])))))
           for e in eps}
    json.dump(idx, open(os.path.join(OUT, "assets", "busqueda.json"), "w", encoding="utf-8"), ensure_ascii=False)

    def w(path, content):
        full = os.path.join(OUT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w", encoding="utf-8").write(content)

    w("index.html", build_index(show, eps))
    for e in eps:
        w(f"episodios/{e['slug']}/index.html", build_episode(e, eps, show))
    for s in CFG["sectores"]:
        if any(e["sector"] == s["slug"] for e in eps):
            w(f"temas/{s['slug']}/index.html", build_sector(s, eps, show))
    w("privacidad/index.html", build_legal("privacidad"))
    w("aviso-legal/index.html", build_legal("aviso-legal"))
    w("404.html", build_404())
    w(".nojekyll", "")
    base = site_url()
    if base:
        urls = [""] + [f"episodios/{e['slug']}/" for e in eps] + \
               [f"temas/{s['slug']}/" for s in CFG["sectores"] if any(e["sector"] == s["slug"] for e in eps)] + \
               ["privacidad/", "aviso-legal/"]
        w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"  <url><loc>{esc(base + u)}</loc></url>\n" for u in urls) + "</urlset>\n")
        w("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n")
    else:
        w("robots.txt", "User-agent: *\nAllow: /\n")
    if CFG.get("domain"):
        w("CNAME", CFG["domain"])
    print(f"OK: {len(eps)} episodios. Último: {eps[0]['title']}")


if __name__ == "__main__":
    main()
