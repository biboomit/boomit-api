import asyncio
import json
from playwright.async_api import async_playwright

def vega_html_template(vega_spec):
    return f"""
    <html>
    <head>
      <script src='https://cdn.jsdelivr.net/npm/vega@5'></script>
      <script src='https://cdn.jsdelivr.net/npm/vega-lite@5'></script>
      <script src='https://cdn.jsdelivr.net/npm/vega-embed@6'></script>
    </head>
    <body>
      <div id='vis'></div>
      <script>
        const spec = {json.dumps(vega_spec)};
        vegaEmbed('#vis', spec).then(function(result) {{
          window.setTimeout(() => {{
            window.callPhantom && window.callPhantom();
          }}, 1000);
        }});
      </script>
    </body>
    </html>
    """

async def render_vega_lite_to_png(vega_spec) -> bytes:
    html = vega_html_template(vega_spec)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 800, "height": 500})
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_selector("#vis canvas, #vis svg")
        # Esperar a que el gráfico se renderice
        await asyncio.sleep(1)
        # Tomar screenshot del div del gráfico
        element = await page.query_selector("#vis")
        png_bytes = await element.screenshot(type="png")
        await browser.close()
        return png_bytes
