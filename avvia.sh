#!/usr/bin/env bash
# Avvia Imbeccata e apre il browser.
#   ./avvia.sh [porta]          (default 8766)
#   NO_BROWSER=1 ./avvia.sh     non apre il browser
# Al primo avvio crea l'ambiente Python (.venv) e installa le dipendenze.
set -euo pipefail
cd "$(dirname "$0")"

PORTA="${1:-8766}"
URL="http://localhost:$PORTA"

apri() {
  [ -n "${NO_BROWSER:-}" ] && return
  if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL"; fi
}

# già in esecuzione? apri solo il browser
if curl -fs "$URL/api/opere" >/dev/null 2>&1; then
  echo "Imbeccata è già in esecuzione su $URL"
  apri
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  PY="$(command -v python3.12 || true)"
  if [ -z "$PY" ]; then
    echo "Serve Python 3.12 (brew install python@3.12)." >&2
    exit 1
  fi
  echo "Primo avvio: creo l'ambiente Python e installo le dipendenze."
  echo "Servono alcuni GB di spazio (torch) e qualche minuto."
  read -r -p "Continuo? [s/N] " r
  [[ "$r" =~ ^[sSyY]$ ]] || exit 1
  "$PY" -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "Imbeccata su $URL  (Ctrl+C per fermare)"
( sleep 1.5; apri ) &
exec .venv/bin/python -I src/server.py "$PORTA"
