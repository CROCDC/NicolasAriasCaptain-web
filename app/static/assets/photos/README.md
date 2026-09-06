# Fotos del sitio

Acá van las fotos del capitán. **No hay que tocar ningún template**: el sitio lee
`app/static/data/gallery.json`, y cada entrada de ese archivo dice qué nombre de
archivo espera. Mientras el archivo no exista, esa foto se muestra como un marco
con la leyenda "Foto en camino"; en cuanto aparece, se muestra la foto.

## Cómo agregar una foto

1. Exportá la imagen en **WebP** (o JPG si no tenés WebP a mano).
2. Guardala en esta carpeta con el nombre exacto que figura en `gallery.json`.
3. Recargá el sitio. Listo.

Para ver qué falta: `make photos`

## Qué espera cada slot

| Archivo | Dónde va | Formato sugerido |
|---|---|---|
| `hero.webp` | Fondo de la portada | Horizontal 2400×1350, con aire arriba |
| `retrato.webp` | Columna "Sobre mí" | Vertical 900×1200 |
| `servicio-patron.webp` | Tarjeta "Patrón a bordo" | Horizontal 1200×900 |
| `servicio-traslado.webp` | Tarjeta "Traslados" | Horizontal 1200×900 |
| `servicio-salida.webp` | Tarjeta "Salidas" | Horizontal 1200×900 |
| `galeria-01.webp` … `galeria-06.webp` | Galería | Horizontal 1600×1067 |
| `og-image.jpg` | Vista previa al compartir el link | **1200×630 exactos** |

## Peso

Ninguna imagen debería superar **400 KB**. Una foto de 6 MB salida de la cámara
hace que la página tarde varios segundos en un celular con datos, que es donde
la va a abrir la mayoría. Redimensionar y exportar a WebP con calidad 80 suele
dejarla en 150–250 KB sin diferencia visible.

## Textos alternativos

El `alt` de cada foto está escrito en `gallery.json`. Si cambiás la foto por otra
que muestra otra cosa, cambiá también ese texto: es lo que leen los buscadores y
quienes navegan con lector de pantalla.
