"""The strings the captain can rewrite without waiting for a deploy.

Every default here is the text the page already showed, so a database with no
overrides renders exactly what the templates rendered before — the registry is
the source of truth and the table only ever holds changes.

Two rules worth knowing before adding to this file:

* **A key is an API.** It is the primary key of the override row, so renaming
  one silently drops whatever was written there. New copy is a new key.
* **Markup stays in the template.** A headline that breaks across two lines is
  two fields, not one field with a ``<br>`` in it: the editor should be typing
  words, not tags, and a stray tag in a ``line`` field renders escaped anyway.

What is *not* here: the phone number, the email, the port and the figures.
Those live in ``app/data/site.json`` because they are data rather than prose —
the same number is read by the WhatsApp links, the schema and the footer, and
having two places to change it is how a site ends up showing two numbers.
"""

import json
import os

from sitecopy import Group, Registry, Section, TextField

#: The photographs are declared once, in the manifest the site already reads.
#: Building the panel's fields from it rather than retyping them here is what
#: keeps a photograph from existing under two names.
_MANIFEST = os.path.join(os.path.dirname(__file__), "static", "data", "gallery.json")
_PHOTO_URL = "/static/assets/photos/"

_PHOTO_LABELS = {
    "hero": "Portada — el medallón",
    "retrato": "Bitácora — el retrato",
    "servicio-patron": "Servicios — patrón a bordo",
    "servicio-traslado": "Servicios — traslados",
    "servicio-salida": "Servicios — salidas",
    "og": "La imagen que se ve al compartir el link",
}


def _photo_fields() -> tuple[TextField, ...]:
    """One image field per declared photograph, defaulting to the shipped file.

    A photograph replaced from the panel keeps its width and height — the size
    is read off the uploaded file — but loses its responsive variants, because
    those are generated ahead of time by scripts/gen_responsive_images.py and an
    upload has none. The page stays correct and a little heavier; running that
    script over the new file puts the variants back.
    """
    with open(_MANIFEST, encoding="utf-8") as handle:
        slots = json.load(handle)
    return tuple(
        TextField(
            f"foto.{slot['id']}",
            _PHOTO_LABELS.get(slot["id"], slot["caption"]),
            type="image",
            hint=slot["alt"],
            default=_PHOTO_URL + slot["file"],
        )
        for slot in slots
    )


REGISTRY = Registry(groups=(

    Group("portada", "Portada", "Lo primero que se ve al entrar", sections=(
        Section("portada", "Portada", fields=(
            TextField("portada.arco", "Texto curvo sobre el medallón",
                      "Patrón de yates · Río de la Plata",
                      hint="Corto: va sobre un arco y el texto largo no entra."),
            TextField("portada.titulo", "Palabra antes del nombre", "Capitán"),
            TextField("portada.cta_servicios", "Botón izquierdo", "Qué hago"),
            TextField("portada.cta_contacto", "Botón derecho", "Consultar una fecha"),
            TextField("portada.pie", "Línea al pie",
                      "Salidas · Traslados · Patrón a bordo"),
        )),
    )),

    Group("bitacora", "Bitácora", "Quién sos y cómo trabajás", sections=(
        Section("titulo", "Título", fields=(
            TextField("bitacora.titulo_1", "Primera línea", "No alquilo un barco."),
            TextField("bitacora.titulo_2", "Segunda línea (en itálica)", "Lo gobierno."),
        )),
        Section("cuerpo", "El texto", fields=(
            TextField("bitacora.parrafo_1", "Primer párrafo", type="text", default=(
                "Me llamo Nicolás Arias y me gano la vida al timón. Empecé como "
                "tripulante, aprendí mirando a gente que llevaba treinta años en el "
                "agua y hoy gobierno barcos ajenos con el mismo cuidado con el que "
                "gobernaría el propio: es el trabajo, y también es la parte que me "
                "gusta.")),
            TextField("bitacora.parrafo_2", "Segundo párrafo", type="text", default=(
                "El Río de la Plata no perdona la improvisación. Entra la sudestada "
                "sin avisar, la bajante deja bancos donde ayer había agua y el canal "
                "a las seis de la tarde se llena de tráfico que no te va a ceder el "
                "paso. Conocer eso de memoria es la diferencia entre una salida "
                "linda y una salida segura, y es exactamente lo que estás "
                "contratando cuando me subís a bordo.")),
            TextField("bitacora.parrafo_3", "Tercer párrafo", type="text", default=(
                "Trabajo con pocas salidas y sin apuro. Prefiero decirte que hoy no "
                "es el día antes que forzar una jornada que después nadie disfruta: "
                "el río está mañana también.")),
            TextField("bitacora.cierre", "Cierre (en negrita)",
                      "Vos salís a navegar. De lo demás me ocupo yo."),
            TextField("bitacora.firma", "Firma", "— Nicolás"),
        )),
        Section("ficha", "La ficha", note="Los datos de la columna derecha.", fields=(
            TextField("bitacora.ficha.k_titulacion", "Etiqueta: titulación", "Titulación"),
            TextField("bitacora.ficha.k_zona", "Etiqueta: zona", "Zona"),
            TextField("bitacora.ficha.k_puerto", "Etiqueta: puerto base", "Puerto base"),
            TextField("bitacora.ficha.k_embarcaciones", "Etiqueta: embarcaciones",
                      "Embarcaciones"),
            TextField("bitacora.ficha.k_temporada", "Etiqueta: temporada", "Temporada"),
            TextField("bitacora.ficha.titulacion", "Titulación",
                      "Patrón de yate — Prefectura Naval Argentina"),
            TextField("bitacora.ficha.zona", "Zona",
                      "Río de la Plata, Delta, Uruguay y costa atlántica"),
            TextField("bitacora.ficha.embarcaciones", "Embarcaciones",
                      "Veleros y lanchas hasta 45 pies"),
            TextField("bitacora.ficha.temporada", "Temporada",
                      "Todo el año, según pronóstico"),
        )),
    )),

    Group("servicios", "Servicios", "Las tres maneras de contratarte", sections=(
        Section("intro", "Encabezado", fields=(
            TextField("servicios.titulo_1", "Primera línea", "Tres maneras de"),
            TextField("servicios.titulo_2", "Segunda línea (en itálica)",
                      "tenerme a bordo"),
            TextField("servicios.bajada", "Bajada", type="text", default=(
                "Todo se cotiza igual: barco, distancia, días y pronóstico. Escribime "
                "con esos cuatro datos y te paso un número cerrado, sin vueltas ni "
                "sorpresas al final.")),
        )),
        Section("patron", "I — Patrón a bordo", fields=(
            TextField("servicios.patron.titulo", "Título", "Patrón a bordo"),
            TextField("servicios.patron.texto", "Descripción", type="text", default=(
                "Tenés el barco, pero no la matrícula, el tiempo o las horas de agua "
                "para esa salida en particular. Lo gobierno yo. Vos invitás, disfrutás "
                "o mirás cómo se hace.")),
            TextField("servicios.patron.puntos", "Qué incluye", type="lines",
                      hint="Un punto por línea.", default=(
                          "Por jornada o por medio día\n"
                          "Chequeo previo de motor, velas y seguridad\n"
                          "Plan de navegación según viento y marea\n"
                          "Práctica guiada al timón, si querés")),
            TextField("servicios.patron.boton", "Botón", "Consultar"),
        )),
        Section("traslado", "II — Traslados y deliveries", fields=(
            TextField("servicios.traslado.titulo", "Título", "Traslados y deliveries"),
            TextField("servicios.traslado.texto", "Descripción", type="text", default=(
                "Compraste en otro puerto, entrás a invernada o tenés que llegar a una "
                "regata que empieza el viernes. Llevo el barco y te lo entrego donde lo "
                "necesitás, en la fecha que acordamos.")),
            TextField("servicios.traslado.puntos", "Qué incluye", type="lines",
                      hint="Un punto por línea.", default=(
                          "Río de la Plata, Delta, Uruguay y costa atlántica\n"
                          "Parte de estado del barco antes de zarpar\n"
                          "Reporte de posición durante la travesía\n"
                          "Tripulación extra cuando la travesía lo pide")),
            TextField("servicios.traslado.boton", "Botón", "Cotizar"),
        )),
        Section("salida", "III — Salidas y charters", fields=(
            TextField("servicios.salida.titulo", "Título", "Salidas y charters"),
            TextField("servicios.salida.texto", "Descripción", type="text", default=(
                "Un día en el río con barco y patrón incluidos. Un cumpleaños, un "
                "atardecer, un domingo largo, o simplemente las ganas de irse un rato "
                "de la ciudad sin subirse a un avión.")),
            TextField("servicios.salida.puntos", "Qué incluye", type="lines",
                      hint="Un punto por línea.", default=(
                          "Grupos chicos, sin turnos apurados\n"
                          "Recorrido a medida por el río o el Delta\n"
                          "Fondeo para nadar o comer a bordo\n"
                          "Fecha sujeta a pronóstico, siempre")),
            TextField("servicios.salida.boton", "Botón", "Reservar una fecha"),
        )),
    )),

    Group("derrota", "La derrota", "Cómo se arma cada salida", sections=(
        Section("intro", "Encabezado", fields=(
            TextField("derrota.titulo_1", "Primera línea", "El mismo orden,"),
            TextField("derrota.titulo_2", "Segunda línea (en itálica)", "siempre"),
            TextField("derrota.bajada", "Bajada", type="text", default=(
                "Sea un paseo de tres horas o una travesía de tres días, la salida se "
                "arma igual. Nada de esto se improvisa arriba del barco.")),
        )),
        Section("pasos", "Los cuatro pasos", fields=(
            TextField("derrota.paso_1.titulo", "01 — Título", "Hablamos"),
            TextField("derrota.paso_1.texto", "01 — Texto", type="text", default=(
                "Qué barco es, qué querés hacer y cuándo. Si no conviene, te lo digo "
                "en ese momento y no perdemos ninguno de los dos el tiempo.")),
            TextField("derrota.paso_2.titulo", "02 — Título", "Miro el tiempo"),
            TextField("derrota.paso_2.texto", "02 — Texto", type="text", default=(
                "Viento, altura del río y pronóstico a 48 horas. Si el día no da, se "
                "corre la fecha. Es la única regla que no negocio.")),
            TextField("derrota.paso_3.titulo", "03 — Título", "Reviso el barco"),
            TextField("derrota.paso_3.texto", "03 — Texto", type="text", default=(
                "Motor, combustible, jarcia, luces, chalecos y balsa. Lo que falta se "
                "resuelve en el amarre, no en el medio del canal.")),
            TextField("derrota.paso_4.titulo", "04 — Título", "Navegamos"),
            TextField("derrota.paso_4.texto", "04 — Texto", type="text", default=(
                "Al timón el tiempo que haga falta. Si querés aprender, se enseña; si "
                "querés desconectar, ni te enterás de que estoy trabajando.")),
        )),
    )),

    Group("galeria", "Galería", "El encabezado de las fotos", sections=(
        Section("galeria", "Encabezado", fields=(
            TextField("galeria.titulo_1", "Primera línea", "El río,"),
            TextField("galeria.titulo_2", "Segunda línea (en itálica)", "desde cubierta"),
            TextField("galeria.bajada", "Bajada", type="text",
                      default="Fotos de salidas y travesías reales."),
            TextField("galeria.pista", "Indicación al pie", "Deslizá para ver más →"),
            TextField("galeria.aria", "La galería, para lectores de pantalla",
                      "Galería de fotos"),
        )),
    )),

    Group("contacto", "Contacto", "El cierre y el formulario", sections=(
        Section("contacto", "Encabezado", fields=(
            TextField("contacto.titulo_1", "Primera línea", "¿Cuándo"),
            TextField("contacto.titulo_2", "Segunda línea (en itálica)", "zarpamos?"),
            TextField("contacto.bajada", "Bajada", type="text", default=(
                "Contame el barco, la fecha y de dónde a dónde. Respondo el mismo día; "
                "por WhatsApp, casi siempre en el momento.")),
            TextField("contacto.nota", "Nota bajo el botón", type="text", default=(
                "Los datos quedan solo acá. No se comparten ni se usan para mandarte "
                "publicidad.")),
        )),
        Section("datos", "Los tres datos de contacto", fields=(
            TextField("contacto.k_whatsapp", "Etiqueta: WhatsApp", "WhatsApp"),
            TextField("contacto.k_email", "Etiqueta: email", "Email"),
            TextField("contacto.k_puerto", "Etiqueta: puerto base", "Puerto base"),
        ), note="Sólo los rótulos; el número y la dirección se cambian en site.json."),
        Section("formulario", "El formulario", fields=(
            TextField("form.nombre", "Nombre", "Nombre"),
            TextField("form.nombre_ph", "Nombre — texto de ejemplo", "Tu nombre"),
            TextField("form.email", "Email", "Email"),
            TextField("form.email_ph", "Email — texto de ejemplo", "tu@email.com"),
            TextField("form.telefono", "Teléfono", "Teléfono"),
            TextField("form.telefono_opcional", "Teléfono — aclaración", "(opcional)"),
            TextField("form.telefono_ph", "Teléfono — texto de ejemplo", "+54 9 11 ..."),
            TextField("form.servicio", "Qué necesitás", "Qué necesitás"),
            TextField("form.servicio_vacio", "Opción inicial", "Elegí una opción"),
            TextField("form.servicio_patron", "Opción: patrón", "Patrón a bordo"),
            TextField("form.servicio_traslado", "Opción: traslado", "Traslado / delivery"),
            TextField("form.servicio_salida", "Opción: salida", "Salida o charter"),
            TextField("form.servicio_otro", "Opción: otra", "Otra consulta"),
            TextField("form.mensaje", "Mensaje", "Mensaje"),
            TextField("form.mensaje_ph", "Mensaje — texto de ejemplo",
                      "Barco, fecha tentativa y de dónde a dónde."),
            TextField("form.boton", "Botón de envío", "Enviar consulta"),
        ), note=("Los mensajes de error y el aviso de \"gracias\" no están acá: los "
                 "escribe el servidor cuando valida, y cambiarlos es tocar código.")),
    )),

    Group("navegacion", "Navegación", "Nombres de sección y barra", icon="≡", sections=(
        Section("secciones", "Nombres de las secciones", fields=(
            TextField("seccion.bitacora", "I — Bitácora", "Bitácora"),
            TextField("seccion.servicios", "II — Servicios", "Servicios"),
            TextField("seccion.derrota", "III — La derrota", "La derrota"),
            TextField("seccion.galeria", "IV — Galería", "Galería"),
            TextField("seccion.contacto", "V — Contacto", "Contacto"),
        ), note=("Cada nombre se usa en tres lugares a la vez: el índice, el "
                 "encabezado de la sección y el pie. Cambiándolo acá cambian los "
                 "tres — que es lo que hay que hacer, porque si se desincronizan "
                 "el menú lleva a una sección que se llama de otra manera.")),
        Section("barra", "La barra de arriba", fields=(
            TextField("barra.coordenadas", "Coordenadas", "34°28′ S · 58°30′ O",
                      hint="Las del puerto base."),
            TextField("barra.indice", "Botón que abre el índice", "Índice"),
            TextField("barra.cerrar", "Botón que lo cierra", "Cerrar ✕"),
            TextField("barra.saltar", "Salto al contenido", "Saltar al contenido",
                      hint="No se ve; lo usa quien navega con teclado o lector de pantalla."),
            TextField("menu.aria", "El índice, para lectores de pantalla", "Secciones"),
        )),
    )),

    Group("error", "Página no encontrada", "Un link roto", icon="?", sections=(
        Section("error", "El 404", fields=(
            TextField("error.pestana", "Título de la pestaña", "Fuera de la carta"),
            TextField("error.titulo", "Título", "Esta página quedó fuera de la carta"),
            TextField("error.texto", "Texto", type="text", default=(
                "El enlace no lleva a ningún puerto conocido. Volvé al inicio y "
                "seguimos desde ahí.")),
            TextField("error.boton", "Botón", "Volver al inicio"),
        )),
    )),

    Group("pie", "Pie de página", "El cierre de la página", icon="_", sections=(
        Section("pie", "El pie", fields=(
            TextField("pie.derechos", "Línea de copyright",
                      "Todos los derechos reservados."),
        )),
    )),

    Group("fotos", "Fotos", "Las imágenes del sitio", icon="◎", sections=(
        Section("fotos", "Las fotos", fields=_photo_fields(),
                note=("Reemplazar una foto acá cambia la que se ve. Conviene "
                      "mandarla ya recortada: las de los medallones se recortan "
                      "en círculo, así que lo que quede en las esquinas se pierde.")),
    )),

))
