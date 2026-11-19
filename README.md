# Web de Historias Profesionales

Web estática que se genera sola a partir del RSS de Spotify for Creators, el canal de YouTube, Apple Podcasts e iVoox. Al publicar un episodio no hay que tocar nada: la web se actualiza dos veces al día (o al momento, con un botón).

## Qué genera

- **Portada** (una sola página): último episodio, todos los episodios con buscador (también busca dentro de lo que se dice en cada episodio) y filtros por tema, preguntas de la audiencia, sobre el pódcast (con preguntas frecuentes) y sobre mí.
- **Una página por episodio** (`/episodios/30-francesca-schipani/`): enlaces a cada plataforma, vídeo, descripción, temas clave, transcripción completa y episodios relacionados. Es lo que más ayuda a salir en Google.
- **Páginas por tema** (`/temas/salud/`…), **privacidad**, **aviso legal** y **404**.
- **Para Google y redes:** `sitemap.xml`, `robots.txt`, datos estructurados e imagen de vista previa propia para cada episodio al compartir el enlace.

## Qué hay en la carpeta

| Archivo | Para qué |
|---|---|
| `config.json` | Textos, correo, enlaces, temas, preguntas frecuentes, «Sobre mí», dominio. **Es lo que se edita a mano.** |
| `data/sectores.json` | Tema de cada episodio. Los nuevos se adivinan por la profesión; para corregir uno, cambia su línea. |
| `data/enlaces.json` | Enlaces de cada episodio en Spotify, Apple, Amazon e iVoox. **Amazon se añade a mano** (ver abajo). |
| `data/youtube.json`, `data/transcripciones/` | Se rellenan solos. No tocar. |
| `build.py` | Genera la web en `_site/` (Python). |
| `assets/` | Estilos, logo, tipografías, foto, iconos. |
| `workflow-deploy.yml` | Automatismo de publicación (va en `.github/workflows/deploy.yml` en GitHub). |
| `fixtures/` | Datos de prueba para generar la vista previa sin internet. |

## Publicarla por primera vez (≈10 minutos)

1. Crea una cuenta en **github.com** (con historiasprofesionales@gmail.com, por ejemplo).
2. Arriba a la derecha, **+ → New repository**. Nombre: `historiasprofesionales` (en minúsculas, sin espacios). Márcalo **Public** y pulsa **Create repository**.
3. En el repositorio vacío, pulsa **uploading an existing file**. Arrastra **todo el contenido de esta carpeta `Web`** (menos `workflow-deploy.yml`). Abajo, **Commit changes**.
4. **Add file → Create new file**. En el nombre escribe exactamente `.github/workflows/deploy.yml` (las barras crean las carpetas). Pega dentro el contenido de `workflow-deploy.yml`. **Commit changes**.
5. **Settings → Pages** (menú izquierdo). En «Build and deployment → Source» elige **GitHub Actions**.
6. Pestaña **Actions → Publicar web → Run workflow**. En 2-3 minutos aparece en verde.
7. Tu web estará en `https://TU-USUARIO.github.io/historiasprofesionales/`.

La primera vez tarda algo más: descarga las 30 transcripciones y genera las imágenes.

## Día a día

- **Episodio nuevo:** nada. En ≤12 h aparece solo. Para que salga al momento: Actions → Publicar web → Run workflow.
- **Amazon Music (único paso manual):** abre `data/enlaces.json` en GitHub (icono del lápiz) y, dentro de `"amazonmusic"`, añade una línea con el número y el enlace completo del episodio, por ejemplo `"31": "https://music.amazon.com/podcasts/…/episodes/…/historias-profesionales-episodio-31-…",` → Commit. Hasta entonces el episodio no muestra el botón de Amazon.
- **Preguntas de la audiencia:** hoja «Preguntas de la audiencia - Historias Profesionales» (cuenta historiasprofesionales@gmail.com). Escribe `sí` en **Publicar** para que salga en la web (tarda ~5 min) y el número del episodio en **Respondida en**. No toques la pestaña **Web**.
- **Portada de un episodio que no está en Spotify:** sube la imagen como `assets/portadas/N.jpg`.
- **Cambiar textos:** `config.json` en GitHub → lápiz → Commit. La web se regenera sola.

## Si algo falla

- Si la generación falla (por ejemplo, el RSS no responde), **la web no se rompe**: sigue la versión anterior y GitHub te manda un correo «Run failed». Normalmente basta con volver a lanzar el workflow más tarde.
- Si el RSS llega casi vacío (menos de 5 episodios), el proceso se para a propósito para no publicar una web vacía.

## Dominio propio (cuando lo compres)

1. Compra el dominio (p. ej. `historiasprofesionales.es` en DonDominio, Namecheap o Cloudflare; ~10-15 €/año).
2. En `config.json`: `"site_url": "https://historiasprofesionales.es"` y añade `"domain": "historiasprofesionales.es"`.
3. En el panel del dominio, DNS: cuatro registros **A** a `185.199.108.153`, `185.199.109.153`, `185.199.110.153` y `185.199.111.153`, y un **CNAME** `www` → `TU-USUARIO.github.io`.
4. GitHub → Settings → Pages → **Custom domain**: escribe el dominio → Save. Cuando salga el check verde, marca **Enforce HTTPS**.
5. Da de alta la web en **Google Search Console** (search.google.com/search-console) y envía `https://historiasprofesionales.es/sitemap.xml`.

## Estadísticas de visitas (opcional, sin cookies)

1. Crea una cuenta gratis en **goatcounter.com** y elige un código (p. ej. `historiasprofesionales`).
2. En `config.json` pon `"goatcounter": "historiasprofesionales"`. La web empieza a contar visitas sin cookies (y la política de privacidad lo menciona sola).

## Probar en tu ordenador (opcional)

`python build.py --rss-file fixtures/rss.xml --yt-file fixtures/yt.xml` genera `_site/` con datos de prueba (sin internet). Abre `_site/index.html`.
