import pdfplumber, json, re
from collections import Counter

ports = Counter()
commodities = Counter()
rows_out = []

with pdfplumber.open('/workspace/cola-buques-rosario/data/vessel_update.pdf') as pdf:
    print('pages', len(pdf.pages))
    for i, p in enumerate(pdf.pages):
        tables = p.extract_tables() or []
        for table in tables:
            for row in table:
                if not row or not row[0]:
                    continue
                if str(row[0]).strip().upper() in ('PORT', '') or row[0] is None:
                    continue
                if len(row) < 9:
                    continue
                vessel = (row[2] or '').strip()
                if not vessel or vessel.upper() == 'NIL':
                    continue
                port = (row[0] or '').strip()
                term = (row[1] or '').strip()
                eta = (row[3] or '').strip()
                etb = (row[4] or '').strip()
                etf = (row[5] or '').strip()
                ops = (row[6] or '').strip()
                tons = (row[7] or '').strip()
                commodity = (row[8] or '').strip()
                dest = (row[9] or '').strip() if len(row)>9 else ''
                origin = (row[10] or '').strip() if len(row)>10 else ''
                charterer = (row[11] or '').strip() if len(row)>11 else ''
                ports[port] += 1
                commodities[commodity] += 1
                rows_out.append({
                    'port': port, 'terminal': term, 'vessel': vessel,
                    'eta': eta, 'etb': etb, 'etf': etf, 'ops': ops,
                    'tons_raw': tons, 'commodity': commodity,
                    'destination': dest, 'origin': origin, 'charterer': charterer
                })

print('TOTAL VESSEL ROWS', len(rows_out))
print('PORTS', dict(ports))
print('COMMODITIES', dict(commodities))
print('SAMPLE', json.dumps(rows_out[:3], ensure_ascii=False, indent=2))
print('TONS SAMPLES', [r['tons_raw'] for r in rows_out[:20]])
