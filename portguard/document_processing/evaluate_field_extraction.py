#!/usr/bin/env python3
"""Evaluate extracted field values against PortGuard synthetic ground truth.

Usage:
  python scripts/evaluate_field_extraction.py predictions.json

Accepted predictions format is a JSON array or JSONL records such as:
  {"document_id":"001-DG","fields":{"container_number":"DEMU1234560","un_number":"UN 1760"}}
Only fields present in each document's ground truth are scored.
"""
ROOT = Path(__file__).resolve().parents[2]

GT = json.loads((ROOT / 'portguard_ocr_starter' / 'ground_truth' / 'labels.json')
    .read_text(encoding='utf-8')
)

def norm(v):
    if v is None: return ''
    s=unicodedata.normalize('NFKC',str(v)).upper().strip()
    s=s.replace('\u2013','-').replace('\u2014','-')
    s=re.sub(r'\s+',' ',s)
    # Punctuation/spacing normalization for common identifiers.
    s=re.sub(r'\bUN\s*[-:]?\s*(\d{4})\b',r'UN \1',s)
    return s

def load_predictions(p):
    text=Path(p).read_text(encoding='utf-8-sig').strip()
    if not text: return []
    try:
        obj=json.loads(text)
        return obj if isinstance(obj,list) else [obj]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]

if len(sys.argv)!=2:
    print('Usage: python scripts/evaluate_field_extraction.py predictions.json')
    sys.exit(2)
preds={x.get('document_id'):x.get('fields',{}) for x in load_predictions(sys.argv[1])}
rows=[]; total=correct=0
for r in GT:
    d=r['document_id']; p=preds.get(d,{})
    for k,expected in r['expected_fields'].items():
        got=p.get(k,'')
        ok=norm(got)==norm(expected)
        total+=1; correct+=int(ok)
        rows.append((d,k,expected,got,ok))
print(f'Field exact-match accuracy: {correct}/{total} = {correct/total:.1%}' if total else 'No fields scored.')
print(f'Documents with predictions: {sum(1 for d in preds if d in {r["document_id"] for r in GT})}/{len(GT)}')
errors=[x for x in rows if not x[4]]
print(f'Field mismatches or missing predictions: {len(errors)}')
for d,k,e,g,ok in errors[:40]: print(f'- {d} | {k} | expected={e!r} | got={g!r}')
