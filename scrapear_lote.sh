#!/bin/bash
# Uso: ./scrapear_lote.sh 2026-12-31 2027-01-20

if [ $# -eq 0 ]; then
    echo "❌ Uso: $0 fecha1 fecha2 ..."
    echo "Ejemplo: $0 2026-12-31 2027-01-20"
    exit 1
fi

FECHAS="$@"
FECHAS_COMA=$(echo "$FECHAS" | tr ' ' ',')

echo "════════════════════════════════════════════════"
echo "  📅 SCRAPEANDO LOTE"
echo "  Fechas: $FECHAS"
echo "════════════════════════════════════════════════"
echo ""

cd ~/Proyectos/scraper_precios_autos
source venv/bin/activate 2>/dev/null || true

python3 -c "
import sys
sys.path.insert(0, '.')
import logging
logging.disable(logging.CRITICAL)
from scraper_precios import escribir_fechas_activas
fechas = '$FECHAS_COMA'.split(',')
escribir_fechas_activas(fechas)
print(f'✅ {len(fechas)} fechas configuradas')
"

echo ""
FIRST=1
for FECHA in $FECHAS; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📅 $FECHA"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ $FIRST -eq 1 ]; then
        python3 scraper_precios.py --fecha "$FECHA" --plataformas expedia \
            --duraciones 3,5,7,15,21,30 --fechas-lote "$FECHAS_COMA" -v
        FIRST=0
    else
        python3 scraper_precios.py --fecha "$FECHA" --plataformas expedia \
            --duraciones 3,5,7,15,21,30 -v
    fi
    sleep 15
done

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ COMPLETADO"
echo "════════════════════════════════════════════════"
cat fechas_activas.txt
echo ""
echo "🚀 SIGUIENTE:"
echo "  git add precios_competencia.db fechas_activas.txt app_dashboard.py scraper_precios.py"
echo "  git commit -m 'Fechas: $FECHAS'"
echo "  git push"
