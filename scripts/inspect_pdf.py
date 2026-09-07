import pdfplumber
with pdfplumber.open('/workspace/cola-buques-rosario/data/vessel_update.pdf') as pdf:
    print('pages', len(pdf.pages))
    for i, p in enumerate(pdf.pages[:3]):
        print('---PAGE', i, '---')
        t = p.extract_text() or ''
        print(t[:3500])
        tables = p.extract_tables()
        print('tables', len(tables) if tables else 0)
        if tables:
            for ti, table in enumerate(tables[:2]):
                print('TABLE', ti, 'rows', len(table))
                for row in table[:10]:
                    print(row)
