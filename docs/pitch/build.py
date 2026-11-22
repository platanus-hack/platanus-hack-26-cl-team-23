# Genera deck.html (autocontenido, para presentar sin internet) desde deck-src.html:
# incrusta las fuentes y las imágenes locales que existan.
import base64, pathlib, re
here = pathlib.Path(__file__).parent
s = (here / 'deck-src.html').read_text()
for f in ['inter', 'geistmono-500']:
    b = base64.b64encode((here / f'fonts/{f}.woff2').read_bytes()).decode()
    s = s.replace(f'url(fonts/{f}.woff2)', f'url(data:font/woff2;base64,{b})')
def img(m):
    p = here / m.group(1)
    if not p.exists():
        return m.group(0)
    mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png'}[p.suffix[1:].lower()]
    return f'src="data:image/{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"'
s = re.sub(r'src="([\w/.-]+\.(?:jpg|jpeg|png))"', img, s)
(here / 'deck.html').write_text(s)
print('deck.html listo')

# Versión para Artifact (comentarios en claude.ai): sin doctype/html/head/body; el visor pone el esqueleto.
# Además sigue el tema del visor si nadie eligió con la tecla D.
a = s
for tag in ['<!doctype html>\n', '<html lang="es">\n', '<head>\n', '</head>\n', '<body>\n', '</body>\n', '</html>\n']:
    a = a.replace(tag, '', 1)
a = re.sub(r'<meta charset="utf-8">\n<meta name="viewport"[^>]*>\n', '', a)
a = a.replace(
    "try { if (localStorage.getItem('trazada-tema') === 'oscuro') document.body.classList.add('dark'); } catch (e) {}",
    "let tema = null; try { tema = localStorage.getItem('trazada-tema'); } catch (e) {}\n"
    "  const r = document.documentElement.dataset.theme;\n"
    "  if (tema === 'oscuro' || (!tema && (r === 'dark' || (!r && matchMedia('(prefers-color-scheme: dark)').matches)))) document.body.classList.add('dark');")
a = a.replace('<title>Trazada · Pitch</title>', '<title>Pitch de Trazada</title>', 1)
(here / 'deck-artifact.html').write_text(a)
print('deck-artifact.html listo')
