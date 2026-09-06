# Convenciones del proyecto

## Estructura

```
NicolasAriasCaptain-web/
├── app/
│   ├── __init__.py          # importa create_app y expone app = create_app()
│   ├── factory.py           # fábrica; db y migrate a nivel de módulo
│   ├── routes.py            # una sola función register_routes(app)
│   ├── data/site.json       # datos de contacto y copy corto
│   ├── models/              # entidades ORM, re-exportadas en __init__
│   ├── repositories/        # acceso a datos, solo métodos estáticos
│   ├── services/            # lógica que no es ni ruta ni tabla
│   ├── templates/           # index.html, 404.html, _macros.html
│   └── static/              # css, js, data, assets
├── tests/
├── scripts/
├── docs/
├── run.py
└── requirements.txt
```

## Código

- **Python 3.12** (el `Makefile` lo fija; no usar 3.13+ mientras `greenlet` no acompañe).
- **Type hints** en toda función y método.
- **PEP 8**, máximo 100 columnas, verificado con `make lint`.
- **Comentarios y docstrings en inglés**; los textos que ve el usuario, en español.
- Imports absolutos dentro de `app/`.

## Patrón de fábrica

`db` y `migrate` se instancian a nivel de módulo en `factory.py` para que los
modelos puedan importarlos sin ciclos. Las extensiones se inicializan con
`init_app(app)` dentro de `create_app()`.

## Repositorios

Cada entidad tiene una clase repositorio con **métodos estáticos**, sin estado
de instancia. Las rutas no hablan con `db.session` directamente.

## Rutas

Todas viven en `app/routes.py`, dentro de `register_routes(app)`. Sin
blueprints mientras el sitio siga siendo una página.

## Migraciones

Los cambios de esquema se registran en `app.factory._MIGRATIONS` y se aplican
una sola vez al arrancar, anotados en la tabla `schema_migrations`. Se agregan
al final de la lista: nunca se edita ni se reordena una ya aplicada. `create_all`
no altera tablas existentes — para eso está esa lista.

## Frontend

- Variables CSS para todos los tokens de diseño; ningún color escrito a mano en una regla.
- La geometría de los motivos (anillo graduado, arco de letras, indicador) sale
  de `app/services/emblem.py`: trigonometría en un template no se lee ni se
  testea.
- `critical.css` va embebido en el `<head>`; el resto se carga asíncrono.
- Sin jQuery ni frameworks. `fetch()` para los formularios, JSON de ida y de vuelta.
- El estado inicial de las animaciones cuelga de la clase `js` en `<html>`: sin
  JavaScript la página se ve entera, nunca en blanco.
- Breakpoints: 900 px (columnas a una sola), 720 px (barra compacta), 560 px (teléfono).
- El índice es una capa a pantalla completa en todos los anchos: al abrirlo el
  foco entra y queda atrapado adentro, y al cerrarlo vuelve al botón.

## Fotos

Se declaran en `app/static/data/gallery.json` y se guardan en
`app/static/assets/photos/`. Una foto que todavía no está se dibuja como
placeholder — nunca como imagen rota. `make photos` dice qué falta.

## Tests

- `tests/` no es un paquete: los módulos hermanos se importan por nombre.
- La suite corre contra el mismo motor que producción (SQLite sobre archivo) y
  aplica las migraciones reales del proyecto.
- Los tests que manejan un navegador llevan `@pytest.mark.slow` y se saltan con
  un mensaje claro si Playwright no tiene navegador instalado.

## Pipeline

`Jenkinsfile` construye la imagen, corre la suite **dentro de la imagen que va a
desplegar** y recién después levanta el contenedor y verifica `/health`. Una
falla en los tests deja el sitio en producción intacto.
