# Capitán Nicolás Arias — sitio web

Sitio de presentación de **Nicolás Arias, patrón de yates**: quién es, qué
servicios ofrece y un formulario de contacto que guarda las consultas.

Mismo stack que Kailua Sailing (Flask + Jinja + CSS propio + Playwright +
Docker/Jenkins), con identidad visual propia.

---

## Estado

Esqueleto completo y funcionando: portada, secciones, formulario que persiste
en base de datos, tests y despliegue. **Faltan las fotos y algunos datos
reales** — todo lo pendiente está marcado abajo.

---

## Arranque rápido

```sh
make install     # crea venv/ e instala dependencias
make dev         # levanta el servidor en un puerto aleatorio (5000-9000)
```

Otros comandos:

| Comando | Qué hace |
|---|---|
| `make test` | Toda la suite |
| `make test-fast` | Todo menos los tests de navegador |
| `make browser` | Descarga el Firefox que usa Playwright |
| `make photos` | Lista las fotos que el sitio todavía espera |
| `make lint` | pycodestyle, 100 columnas |
| `make coverage` | Cobertura de la suite rápida |
| `make screenshots` | Reescribe el baseline visual de este renderer |

---

## Cómo agregar las fotos

No hay que tocar ningún template. El sitio lee
`app/static/data/gallery.json`, y cada entrada dice qué archivo espera. Mientras
el archivo no exista, esa foto se muestra como un marco con la leyenda "Foto en
camino"; en cuanto aparece, se muestra la foto.

```sh
make photos                       # ver qué falta
cp mi-foto.webp app/static/assets/photos/retrato.webp
```

Detalle de tamaños y pesos: `app/static/assets/photos/README.md`.

---

## Qué falta reemplazar

| Dónde | Qué |
|---|---|
| `app/data/site.json` | WhatsApp, email, Instagram, dominio y los números de la sección "Sobre mí". La clave `placeholders` lista exactamente cuáles siguen siendo de relleno. |
| `app/templates/index.html` | Los bloques marcados con `TODO copy` y `TODO datos`: la biografía real y la titulación exacta. |
| `docker-compose.yml` | `VIRTUAL_HOST` / `LETSENCRYPT_HOST` con el dominio real. |
| `app/static/assets/photos/` | Las fotos (ver arriba). |
| `app/static/assets/favicon.svg` | Solo si más adelante se quiere otro ícono. |

El emblema que pasaste quedó **solo como inspiración**: no está en el sitio ni
se lo nombra en ningún lado. La marca del sello, el pie y el favicon son un
dibujo propio (aguja de cuatro puntas dentro de un anillo graduado).

---

## Identidad visual

El punto de partida fue el emblema circular del capitán: **inspiración, no
copia**. De ahí sale el vocabulario — un anillo graduado, una aguja, letras
montadas sobre un arco, tres líneas de agua — y de ahí sale la gama, corrida a
propósito para no repetir sus colores exactos.

Todo el sitio está construido sobre esa idea: **una rosa de los vientos**.

| Rol | Color |
|---|---|
| Arena (fondo claro) | `#f0e7d5` / `#e5d9c2` |
| Petróleo (fondo oscuro) | `#10333a` / `#0a2329` |
| Cobre (el grabado) | `#b8762e` |
| Vidrio de mar (el agua) | `#6a97a0` |

Tipografías: **Cinzel** para el sello y la numeración, **Fraunces** para los
títulos, **Karla** para el texto.

Qué hace que no se parezca a Kailua Sailing:

- **Portada clara con un medallón**, no una foto oscura a pantalla completa con
  parallax. La foto va *dentro* del anillo graduado, con el oficio escrito en
  arco por encima.
- **La barra no tiene links**: coordenadas, sello y una sola perilla. La
  navegación es un **índice a pantalla completa** numerado en romanos, igual en
  celular que en escritorio.
- **Los servicios son entradas de ancho completo** que alternan lados, no tres
  tarjetas en fila.
- **Las cifras se leen sobre un arco graduado**, no en una fila de números
  grandes.
- **La galería es un riel que se desliza** con dos alturas sobre una misma
  línea de base, no una grilla.
- **El pie es un sello centrado**, no cuatro columnas de links.
- La regla graduada que separa secciones, la marca de la aguja y las tres
  líneas de agua se dibujan con la geometría de `app/services/emblem.py`, no
  con números escritos a mano en un template.

## Estructura

```
app/
├── factory.py          # create_app, cache, migraciones, globals de Jinja
├── routes.py           # todas las rutas, en register_routes(app)
├── data/site.json      # nombres, teléfonos, links: un solo lugar
├── models/             # ContactMessage
├── repositories/       # acceso a datos, métodos estáticos
├── services/media.py   # el manifiesto de fotos y sus placeholders
├── templates/          # index.html, 404.html, _macros.html
└── static/
    ├── css/            # critical (inline) + deferred + style (noscript)
    ├── js/main.js      # sin frameworks
    ├── data/gallery.json
    └── assets/photos/  # acá van las fotos
tests/                  # pytest + Playwright
scripts/check_photos.py # lo que corre `make photos`
```

Convenciones de código: `docs/CONVENTIONS.md`.

---

## Tests

```sh
make test-fast   # rápido, sin navegador
make browser     # una sola vez
make test        # todo, incluido el navegador
```

Los tests de navegador cubren: que ninguna página tenga scroll horizontal en
cinco anchos distintos, que el menú móvil abra y cierre, que los links de
servicio preseleccionen el formulario y que una consulta llegue a la base.

En una máquina que ya tiene un navegador propio, `BROWSER_EXECUTABLE=/ruta/al/binario`
evita descargar otro.

### Baseline visual (screenshots)

Además hay una **regresión visual**: cada pantalla se compara contra una captura
commiteada, así un cambio de CSS que nadie quiso hacer rompe el build en vez de
esperar a que alguien lo note.

```sh
make screenshots   # reescribe el baseline después de un cambio buscado
```

Mirá el diff antes de commitearlo: para eso está el baseline.

Detalles que hacen que esto sea usable y no una tortura:

- **Un baseline por renderer.** La misma página no da los mismos píxeles en dos
  navegadores ni en dos sistemas operativos, así que las capturas viven en
  `tests/screenshots/<plataforma>-<navegador>/`. Hoy está commiteado
  `linux-chromium`; un renderer sin set propio escribe uno en la primera
  corrida, avisa, y a partir de que lo commiteás queda cubierto.
- **Las fuentes web están bloqueadas** durante estas pruebas. Si dependieran de
  que Google conteste, el baseline cambiaría con la red.
- **Todo lo que se mueve se congela** antes de la foto, y el año del pie se tapa
  (si no, el 1 de enero se pone todo en rojo solo).
- **Tolerancia**: hasta 0,2% de píxeles distintos es ruido de rasterizado; un
  cambio real de layout mueve miles.

Cuando una comparación falla deja `<pantalla>.actual.png` y `<pantalla>.diff.png`
al lado del baseline (ignorados por git) para poder mirarlos.

---

## Despliegue

`git push` a `main` dispara el workflow de GitHub Actions, que llama al job de
Jenkins. Jenkins construye la imagen, corre la suite **dentro de la imagen que
va a desplegar**, recién ahí levanta el contenedor y verifica `/health`. Si los
tests fallan, el sitio que está andando no se toca.

Variables de entorno en producción: `SECRET_KEY` (obligatoria) y
`DATABASE_URL` (por defecto SQLite en el volumen `/app/instance`).
