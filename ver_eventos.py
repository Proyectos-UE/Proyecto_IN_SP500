"""Muestra los eventos guardados en data/inbox.db.

Uso:  python ver_eventos.py        # los últimos 20
      python ver_eventos.py 50     # los últimos 50
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent / 'data' / 'inbox.db'
COLUMNAS = ['n', 'origen', 'event_id', 'event_type', 'resultado', 'fecha', 'hora']


def main() -> None:
    limite = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 20

    if not DB.exists():
        print(f'No existe {DB}. Arranca la API al menos una vez para que se cree.')
        return

    con = sqlite3.connect(DB)
    try:
        total = con.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]
        filas = con.execute(
            'SELECT rowid, origen, event_id, event_type, resultado, fecha, hora '
            'FROM eventos ORDER BY rowid DESC LIMIT ?', (limite,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f'No se pudo leer la tabla eventos: {e}')
        return
    finally:
        con.close()

    print(f'Eventos guardados: {total}')
    if not filas:
        return
    print(f'Últimos {len(filas)} (el más reciente primero):\n')

    filas = [[str(v) for v in f] for f in filas]
    anchos = [max(len(c), *(len(f[i]) for f in filas)) for i, c in enumerate(COLUMNAS)]
    print('  '.join(c.ljust(anchos[i]) for i, c in enumerate(COLUMNAS)))
    print('  '.join('-' * a for a in anchos))
    for f in filas:
        print('  '.join(v.ljust(anchos[i]) for i, v in enumerate(f)))


if __name__ == '__main__':
    main()