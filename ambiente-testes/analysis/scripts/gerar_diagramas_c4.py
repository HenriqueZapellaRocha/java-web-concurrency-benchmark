"""Gera uma visão C4 de componentes para cada protótipo do TCC 2.

Cada visão tem exatamente uma aplicação Spring Boot como contêiner em escopo.
Os elementos e relações descrevem a estrutura observada nas implementações.
"""

from dataclasses import dataclass
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "figuras"
SIZE = (2600, 1700)

FONT_CANDIDATES = (
    (Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
     Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
     Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
)
REGULAR, BOLD = next(
    ((regular, bold) for regular, bold in FONT_CANDIDATES
     if regular.exists() and bold.exists()),
    (None, None),
)
if REGULAR is None:
    raise RuntimeError("Não foi encontrada uma fonte Arial ou DejaVu Sans.")

INK = "#1C3446"
SECONDARY = "#445C6C"
COMPONENT_FILL = "#E6F3F9"
COMPONENT_STROKE = "#28688C"
EXTERNAL_FILL = "#EFF2F4"
EXTERNAL_STROKE = "#7B8B95"
PAPER = "#FFFFFF"
BOUNDARY_FILL = "#FAFCFD"


@dataclass(frozen=True)
class Variant:
    model: str
    server: str
    execution: str
    controller: str
    cpu: str
    io: str
    mixed: str
    adapter: str
    database_protocol: str


VARIANTS = (
    Variant("M1", "Spring Boot, Spring MVC e Tomcat",
            "Pool de até 200 threads de plataforma na configuração principal",
            "Spring MVC", "Java", "Spring", "Java", "JPA/JDBC", "JDBC"),
    Variant("M2", "Spring Boot, Spring MVC e Tomcat",
            "Threads virtuais habilitadas para as requisições HTTP",
            "Spring MVC", "Java", "Spring", "Java", "JPA/JDBC", "JDBC"),
    Variant("M3", "Spring Boot, Spring WebFlux e Netty",
            "Serviços reativos; cálculo no event loop ou em boundedElastic",
            "Spring WebFlux", "Reactor", "Reactor", "Reactor",
            "R2DBC", "R2DBC"),
)


def face(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD if bold else REGULAR), size)


def fit(draw: ImageDraw.ImageDraw, text: str, maximum: int,
        width: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    size = maximum
    while draw.textbbox((0, 0), text, font=face(size, bold))[2] > width:
        size -= 1
        if size < 24:
            raise ValueError(f"Texto longo demais: {text}")
    return face(size, bold)


def center(draw: ImageDraw.ImageDraw, point: tuple[int, int], text: str,
           font: ImageFont.FreeTypeFont, color: str = INK) -> None:
    draw.text(point, text, font=font, fill=color, anchor="mm")


def node(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int],
         name: str, kind: str, technology: str, description: str,
         external: bool = False) -> None:
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle(rect, radius=20, width=5,
                           fill=EXTERNAL_FILL if external else COMPONENT_FILL,
                           outline=EXTERNAL_STROKE if external else COMPONENT_STROKE)
    cx = (x1 + x2) // 2
    width = x2 - x1 - 28
    center(draw, (cx, y1 + 49), name, fit(draw, name, 47, width, True))
    center(draw, (cx, y1 + 106), f"[{kind} | {technology}]",
           fit(draw, f"[{kind} | {technology}]", 35, width), SECONDARY)
    center(draw, (cx, y1 + 165), description,
           fit(draw, description, 36, width))


def label(draw: ImageDraw.ImageDraw, point: tuple[int, int], text: str) -> None:
    font = face(33, True)
    left, top, right, bottom = draw.textbbox(point, text, font=font, anchor="mm")
    draw.rounded_rectangle((left - 8, top - 6, right + 8, bottom + 6),
                           radius=7, fill=PAPER)
    center(draw, point, text, font, SECONDARY)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int],
          end: tuple[int, int], text: str,
          text_point: tuple[int, int]) -> None:
    angle = atan2(end[1] - start[1], end[0] - start[0])
    base_x = end[0] - 18 * cos(angle)
    base_y = end[1] - 18 * sin(angle)
    draw.line((start, (base_x, base_y)), fill=INK, width=6)
    draw.polygon((end,
                  (base_x + 11 * sin(angle), base_y - 11 * cos(angle)),
                  (base_x - 11 * sin(angle), base_y + 11 * cos(angle))),
                 fill=INK)
    label(draw, text_point, text)


def render(variant: Variant) -> Path:
    image = Image.new("RGB", SIZE, PAPER)
    draw = ImageDraw.Draw(image)

    center(draw, (SIZE[0] // 2, 75),
           f"Diagrama de componentes C4 — {variant.model}", face(63, True))
    draw.rounded_rectangle((115, 185, 2140, 1450), radius=26, width=6,
                           fill=BOUNDARY_FILL, outline=COMPONENT_STROKE)
    draw.text((175, 223),
              f"Aplicação {variant.model} [Contêiner | {variant.server}]",
              font=fit(draw,
                       f"Aplicação {variant.model} [Contêiner | {variant.server}]",
                       47, 1900, True), fill=INK)
    draw.text((175, 282), variant.execution,
              font=fit(draw, variant.execution, 35, 1800), fill=SECONDARY)

    controller_x = (205, 700)
    service_x = (1080, 1530)
    cpu_y = (380, 595)
    io_y = (750, 965)
    mixed_y = (1120, 1335)
    adapter = (1720, 750, 2070, 965)
    postgres = (2210, 750, 2570, 965)

    for name, top, route in (("Controlador CPU", cpu_y, "/cpu"),
                             ("Controlador I/O", io_y, "/io"),
                             ("Controlador misto", mixed_y, "/mixed")):
        node(draw, (controller_x[0], top[0], controller_x[1], top[1]),
             name, "Componente", variant.controller,
             f"Recebe POST {route}")

    node(draw, (service_x[0], cpu_y[0], service_x[1], cpu_y[1]),
         "Serviço CPU", "Componente", variant.cpu, "Executa PBKDF2")
    node(draw, (service_x[0], io_y[0], service_x[1], io_y[1]),
         "Serviço I/O", "Componente", variant.io,
         "Espera, lê e registra evento")
    node(draw, (service_x[0], mixed_y[0], service_x[1], mixed_y[1]),
         "Serviço misto", "Componente", variant.mixed,
         "Calcula SHA-256 e chama I/O")
    node(draw, adapter, "Adaptador I/O", "Componente", variant.adapter,
         "Executa acesso ao banco")
    node(draw, postgres, "PostgreSQL", "Contêiner", "PostgreSQL",
         "Catálogo e eventos", external=True)

    arrow(draw, (700, 488), (1080, 488), "Solicita cálculo", (890, 428))
    arrow(draw, (700, 858), (1080, 858), "Solicita transação", (890, 798))
    arrow(draw, (700, 1228), (1080, 1228), "Solicita composição", (890, 1168))
    arrow(draw, (1305, 1120), (1305, 965), "Chama fluxo de I/O", (1515, 1043))
    arrow(draw, (1530, 858), (1720, 858), "Porta I/O", (1625, 798))
    arrow(draw, (2070, 858), (2210, 858),
          f"SQL / {variant.database_protocol}", (2140, 711))

    draw.line((50, 1540, 2550, 1540), fill="#C9D6DD", width=3)
    center(draw, (SIZE[0] // 2, 1615),
           "Legenda: contorno azul = aplicação; azul = componente interno; cinza = contêiner externo; seta = relação dirigida",
           fit(draw,
               "Legenda: contorno azul = aplicação; azul = componente interno; cinza = contêiner externo; seta = relação dirigida",
               34, 2470), SECONDARY)

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"c4-componentes-{variant.model.lower()}.png"
    image.save(target, dpi=(300, 300), optimize=True)
    return target


if __name__ == "__main__":
    assert len({v.model for v in VARIANTS}) == len(VARIANTS)
    for variant in VARIANTS:
        print(render(variant))
