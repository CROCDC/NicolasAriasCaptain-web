# Fotos del sitio

Acá van las fotos del capitán. **No hay que tocar ningún template**: el sitio lee
`app/static/data/gallery.json`, y cada entrada dice qué nombre de archivo espera.
Mientras el archivo no exista, ese lugar se muestra como un **cuadro gris con la
descripción de la foto que va ahí** — la misma frase que después será su texto
alternativo. En cuanto el archivo aparece, se muestra la foto.

## Cómo agregar una foto

1. Exportá la imagen en **WebP** (o JPG si no tenés WebP a mano).
2. Guardala en esta carpeta con el nombre exacto que figura en `gallery.json`.
3. Recargá el sitio. Listo.

Para ver qué falta: `make photos`

## Qué espera cada lugar

| Archivo | Dónde va | Cómo se recorta |
|---|---|---|
| `hero.webp` | El medallón de la portada | **Círculo** — mandá una cuadrada, 1600×1600 |
| `retrato.webp` | Columna de la bitácora | Vertical 3:4, 900×1200 |
| `servicio-patron.webp` | Entrada "Patrón a bordo" | **Círculo** — cuadrada, 1200×1200 |
| `servicio-traslado.webp` | Entrada "Traslados" | **Círculo** — cuadrada, 1200×1200 |
| `servicio-salida.webp` | Entrada "Salidas" | **Círculo** — cuadrada, 1200×1200 |
| `galeria-01.webp` … `galeria-06.webp` | La galería que se desliza | Alternan vertical 3:4 y cuadrada |
| `og-image.jpg` | Vista previa al compartir el link | **1200×630 exactos** |

En las que se recortan en círculo, dejá aire alrededor del motivo: lo que quede
en las esquinas se pierde.

## Peso

Ninguna imagen debería superar **400 KB**. Una foto de 6 MB salida de la cámara
hace que la página tarde varios segundos en un celular con datos, que es donde
la va a abrir la mayoría. Redimensionar y exportar a WebP con calidad 80 suele
dejarla en 150–250 KB sin diferencia visible.

## Textos alternativos

La descripción de cada foto está en `gallery.json`. Es lo que se ve en el cuadro
gris mientras la foto no está, y lo que leen los buscadores y los lectores de
pantalla cuando ya está. Si cambiás una foto por otra que muestra otra cosa,
cambiá también esa descripción.
