import pdfplumber
from collections import defaultdict
terms = defaultdict(set)
with pdfplumber.open('/workspace/cola-buques-rosario/data/vessel_update.pdf') as pdf:
    for p in pdf.pages:
        for table in (p.extract_tables() or []):
            for row in table:
                if not row or not row[0] or not row[2]:
                    continue
                if str(row[2]).strip().upper() == 'NIL':
                    continue
                if str(row[0]).strip().upper() == 'PORT':
                    continue
                port = (row[0] or '').strip()
                term = (row[1] or '').strip()
                if port in ('SAN LORENZO', 'ROSARIO', 'VILLA CONSTITUCION', 'SAN NICOLAS'):
                    terms[port].add(term)
for port, ts in sorted(terms.items()):
    print('===', port)
    for t in sorted(ts):
        print(' ', t)
