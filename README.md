# Monitor de ahorros · Argentina

Dashboard que junta los indicadores para vigilar el riesgo sobre los ahorros (dólar y brecha, riesgo país, reservas y depósitos en dólares del BCRA) y las fechas clave de 2027.

- **Dashboard:** https://mariopicassodev.github.io/monitor-ahorros/
- **Cómo funciona:** `monitor_ahorros.py` (solo biblioteca estándar de Python 3) lee las fuentes públicas y escribe `data.json`. `docs/index.html` lo muestra. Un GitHub Action lo ejecuta todos los días y publica el resultado en la rama `gh-pages`, que es la que sirve GitHub Pages.

```bash
python3 monitor_ahorros.py            # reporte en la terminal
python3 monitor_ahorros.py --out dir  # además escribe dir/data.json para el dashboard
```

> Información con fines educativos, no es asesoramiento financiero.

## Cómo colaborar

La rama `main` está protegida: **nadie pushea directo, todo cambio entra por pull request** y solo el dueño del repo (@mariopicassodev) puede aprobarlo y mergearlo.

1. Hacé un **fork** del repo.
2. En tu fork creá una rama de trabajo, por ejemplo `develop`, y hacé ahí tus cambios.
3. **Probalo levantando tu propio GitHub Pages** (obligatorio, ver abajo).
4. Abrí el pull request hacia `main` con la descripción completa (ver abajo).

### Cómo probar tus cambios en un GitHub Pages

Todo cambio tiene que verse funcionando antes de pedir el merge.

1. En tu fork, andá a **Actions** y habilitá los workflows si GitHub te lo pide.
2. Entrá a **Actions → Actualizar datos → Run workflow**, elegí tu rama (`develop`) y ejecutalo. Genera los datos con tu versión del script y publica tu `index.html` en la rama `gh-pages` de tu fork.
3. En **Settings → Pages**, elegí como fuente la rama `gh-pages` y la carpeta `/ (root)`.
4. Abrí `https://<tu-usuario>.github.io/monitor-ahorros/` y comprobá que todo se ve y funciona.
5. Sacá un **screenshot o un video corto** de lo que cambió (antes y después si corresponde) y adjuntalo al pull request.

También podés probar sin Pages con `python3 monitor_ahorros.py --out /tmp/prueba` para revisar solo los datos, pero **no reemplaza** el paso del screenshot/video.

### Qué tiene que decir tu pull request

Un PR sin esto no se revisa.

**Si es una mejora o un arreglo:**
- **Qué problema había:** qué estaba mal o faltaba, con un ejemplo concreto.
- **Por qué es un problema:** a quién afecta y qué consecuencia tiene (por ejemplo, “la alerta no saltaba aunque las reservas cayeran 4 semanas”).
- **Qué mejora hiciste:** qué cambiaste y cómo resuelve el problema.
- **Evidencia:** screenshot o video del Pages levantado desde tu fork.

**Si agregás un dato o indicador nuevo:**
- **Por qué es importante:** qué le dice a una persona con ahorros y por qué vale la pena vigilarlo.
- **Cuándo es negativo y cuándo positivo:** el umbral propuesto y la justificación. Tiene que reflejarse también en la sección “Explicación de métricas” del dashboard.
- **Fuente:** de dónde sale el dato (preferentemente oficial y gratuita, sin API key) y con qué frecuencia se actualiza.
- **Evidencia:** screenshot o video del dato mostrándose en tu Pages.

**Si agregás o corregís una fecha del calendario:** incluí un link a la fuente oficial o una noticia confiable que la confirme.

### Reglas generales

- El script debe seguir usando **solo la biblioteca estándar** de Python 3.
- Si una fuente falla, el script no debe cortarse: ese indicador se muestra como “s/d” y los demás siguen funcionando.
- Un PR, un tema. Si son dos cosas distintas, mandá dos PR.
