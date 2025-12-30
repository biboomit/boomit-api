import os
import tempfile
import asyncio
import base64
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from app.utils.vega_lite import render_vega_lite_to_png

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def generate_pdf_from_json(report_json: dict) -> bytes:
    """
    Genera un PDF a partir del JSON estructurado del reporte y gráficos Vega-Lite.
    """
    # Renderizar gráficos Vega-Lite a imágenes base64
    for block in report_json.get("blocks", []):
        for chart in block.get("charts", []):
            vega_spec = chart.get("vega_lite_spec")
            if vega_spec:
                # Renderizar a PNG y codificar en base64
                png_bytes = asyncio.run(render_vega_lite_to_png(vega_spec))
                chart["chart_img_base64"] = base64.b64encode(png_bytes).decode("utf-8")
            else:
                chart["chart_img_base64"] = None
    # Renderizar HTML con Jinja2
    template = env.get_template("report_template.html")
    html_content = template.render(report=report_json)
    # Generar PDF con WeasyPrint
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
        HTML(string=html_content).write_pdf(tmp_pdf.name)
        tmp_pdf.seek(0)
        return tmp_pdf.read()
