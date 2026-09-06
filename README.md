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
| `app/static/assets/favicon.svg` | Si se usa el emblema propio en lugar de la marca dibujada en CSS/SVG. |

El logo circular ("Orza del Plata") no se copió: la marca del sitio —el
`{{ ui.mark() }}` del navbar, el pie y el favicon— es un dibujo propio de la
misma familia (arco, aguja, tres líneas de agua). Si el emblema real tiene que
aparecer tal cual, se agrega como `app/static/assets/logo.svg` y se cambia esa
macro por un `<img>`.

---

## Identidad visual

Deliberadamente distinta a la de Kailua: allá es un sitio oscuro con vidrio y
curvas; acá es **papel y tinta**, como una carta náutica anotada.

| Rol | Color |
|---|---|
| Papel | `#f4ecdd` / `#ece0cb` |
| Tinta | `#142a3a` / `#0d1d29` |
| Latón (acento) | `#c4902f` |
| Acero (agua) | `#5d8ea9` |

Tipografías: **Marcellus** para títulos, **Karla** para texto.

Marcas propias del diseño: el meridiano vertical con las coordenadas del puerto
en la portada, la numeración romana de las secciones (I a V), las tres
hairlines de estela en lugar de olas recortadas, el arco sobre el retrato y la
grilla de carta apenas visible en el fondo.

---

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

---

## Despliegue

`git push` a `main` dispara el workflow de GitHub Actions, que llama al job de
Jenkins. Jenkins construye la imagen, corre la suite **dentro de la imagen que
va a desplegar**, recién ahí levanta el contenedor y verifica `/health`. Si los
tests fallan, el sitio que está andando no se toca.

Variables de entorno en producción: `SECRET_KEY` (obligatoria) y
`DATABASE_URL` (por defecto SQLite en el volumen `/app/instance`).
