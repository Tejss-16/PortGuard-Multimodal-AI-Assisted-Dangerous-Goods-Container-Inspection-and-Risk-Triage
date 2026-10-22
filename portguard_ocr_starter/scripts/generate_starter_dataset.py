from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from PIL import Image, ImageEnhance, ImageFilter
import json, csv, os, math, random, subprocess, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'documents'
CLEAN = ROOT / 'images' / 'clean'
SCAN = ROOT / 'images' / 'scan_like'
GT = ROOT / 'ground_truth'
for p in [DOCS, CLEAN, SCAN, GT]:
    p.mkdir(parents=True, exist_ok=True)

# Synthetic-only identifiers and scenarios. These are illustrative test records, not shipments.
packets = [
    {
      'case_id':'SYN-CASE-001', 'container_number':'DEMU1234560', 'seal_number':'SYNSEAL001',
      'un_number':'UN 1760', 'proper_shipping_name':'CORROSIVE LIQUID, N.O.S.', 'hazard_class':'8', 'packing_group':'II',
      'product_identifier':'PG-SYN-CORR-01', 'shipper':'Example Chemicals Ltd. (fictional)', 'consignee':'Harbour Demo Depot (fictional)',
      'port_of_loading':'Mundra (illustrative)', 'port_of_discharge':'JNPA region (illustrative)',
      'commodity_description':'Synthetic corrosive test liquid', 'packages':'48 drums', 'gross_weight_kg':'12480',
      'marine_pollutant':'Not stated in this synthetic example', 'notes':'Consistent packet for pipeline smoke testing.'
    },
    {
      'case_id':'SYN-CASE-002', 'container_number':'DEMU7654321', 'seal_number':'SYNSEAL002',
      'un_number':'UN 3082', 'proper_shipping_name':'ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.', 'hazard_class':'9', 'packing_group':'III',
      'product_identifier':'PG-SYN-ENV-02', 'shipper':'Sample Maritime Chemicals (fictional)', 'consignee':'Coastal Test Warehouse (fictional)',
      'port_of_loading':'Hazira (illustrative)', 'port_of_discharge':'JNPA region (illustrative)',
      'commodity_description':'Synthetic environmentally hazardous liquid', 'packages':'20 IBCs', 'gross_weight_kg':'18600',
      'marine_pollutant':'Yes (example field)', 'notes':'Intentional mismatch: packing list seal differs from dangerous-goods declaration.'
    },
    {
      'case_id':'SYN-CASE-003', 'container_number':'DEMU2468106', 'seal_number':'SYNSEAL003',
      'un_number':'UN 3077', 'proper_shipping_name':'ENVIRONMENTALLY HAZARDOUS SUBSTANCE, SOLID, N.O.S.', 'hazard_class':'9', 'packing_group':'III',
      'product_identifier':'PG-SYN-ENV-03', 'shipper':'Fictional Bulk Materials Co.', 'consignee':'Example Portside Receiver (fictional)',
      'port_of_loading':'Kandla (illustrative)', 'port_of_discharge':'JNPA region (illustrative)',
      'commodity_description':'Synthetic environmentally hazardous solid', 'packages':'600 bags', 'gross_weight_kg':'15200',
      'marine_pollutant':'Yes (example field)', 'notes':'Intentional mismatch: SDS Section 14 uses UN 3077 while DG declaration uses UN 3082.'
    }
]

# Patch packet 3 DG declaration values intentionally so the per-document ground truth captures the mismatch.

def wrap_text(c, text, x, y, max_width, font='Helvetica', size=9, leading=12, color=colors.black):
    c.setFillColor(color); c.setFont(font, size)
    words = str(text).split()
    lines=[]; line=''
    for word in words:
        candidate = (line + ' ' + word).strip()
        if stringWidth(candidate, font, size) <= max_width or not line:
            line = candidate
        else:
            lines.append(line); line = word
    if line: lines.append(line)
    for l in lines:
        c.drawString(x, y, l); y -= leading
    return y

def draw_watermark(c, width, height):
    c.saveState()
    c.translate(width/2, height/2); c.rotate(32)
    c.setFillColor(colors.Color(0.88,0.88,0.88,alpha=0.50))
    c.setFont('Helvetica-Bold', 30)
    c.drawCentredString(0, 0, 'SYNTHETIC - TEST ONLY')
    c.restoreState()

def common_page(c, title, doc_id, case_id, variant=0):
    W,H=A4
    draw_watermark(c,W,H)
    # Top label is deliberately explicit to avoid confusion with official documents.
    c.setFillColor(colors.HexColor('#102A43'))
    c.rect(0,H-26*mm,W,26*mm,fill=1,stroke=0)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 15)
    c.drawString(18*mm,H-12*mm,'PORTGUARD | SYNTHETIC TEST DATA')
    c.setFont('Helvetica',8.5); c.drawString(18*mm,H-19*mm,'NOT AN OFFICIAL CUSTOMS, CARRIER OR HAZARDOUS-GOODS FORM')
    c.setFillColor(colors.HexColor('#102A43')); c.setFont('Helvetica-Bold', 14)
    c.drawString(18*mm,H-39*mm,title)
    c.setFillColor(colors.HexColor('#52606D')); c.setFont('Helvetica',8)
    c.drawString(18*mm,H-46*mm,f'Document ID: {doc_id}     Linked test case: {case_id}')
    c.setStrokeColor(colors.HexColor('#BCCCDC')); c.line(18*mm,H-50*mm,W-18*mm,H-50*mm)
    return W,H

def draw_field_rows(c, rows, y, left=20*mm, width=170*mm, label_w=53*mm, row_h=12*mm, font_size=9):
    for label,value in rows:
        c.setFillColor(colors.HexColor('#F0F4F8')); c.rect(left,y-row_h+2*mm,width,row_h,fill=1,stroke=0)
        c.setFillColor(colors.HexColor('#334E68')); c.setFont('Helvetica-Bold',font_size)
        c.drawString(left+3*mm,y-5.5*mm,str(label)[:42])
        c.setFillColor(colors.HexColor('#102A43')); c.setFont('Helvetica',font_size)
        # wrapping field value in right cell
        maxw=width-label_w-5*mm
        words=str(value).split(); line=''; lines=[]
        for word in words:
            cand=(line+' '+word).strip()
            if stringWidth(cand,'Helvetica',font_size) <= maxw or not line: line=cand
            else: lines.append(line); line=word
        if line: lines.append(line)
        for i,l in enumerate(lines[:2]): c.drawString(left+label_w,y-5.5*mm-i*4*mm,l)
        c.setStrokeColor(colors.white); c.line(left+label_w-2*mm,y-row_h+2*mm,left+label_w-2*mm,y+2*mm)
        y -= row_h
    return y

def draw_footer(c, y, text='For OCR and information-extraction development only. Do not use for operational, customs or safety decisions.'):
    W,H=A4
    c.setStrokeColor(colors.HexColor('#BCCCDC')); c.line(18*mm,22*mm,W-18*mm,22*mm)
    wrap_text(c,text,18*mm,17*mm,W-36*mm,font='Helvetica',size=7,leading=8,color=colors.HexColor('#627D98'))

def dg_rows(p, dg_un=None):
    un = dg_un or p['un_number']
    if un == 'UN 3082': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.'; cls='9'; pg='III'
    elif un == 'UN 3077': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, SOLID, N.O.S.'; cls='9'; pg='III'
    else: name='CORROSIVE LIQUID, N.O.S.'; cls='8'; pg=p['packing_group']
    return [
      ('Container number',p['container_number']), ('Seal number',p['seal_number']),
      ('UN number',un), ('Proper shipping name',name), ('Hazard class',cls), ('Packing group',pg),
      ('Packages / packaging',p['packages']), ('Gross mass (kg)',p['gross_weight_kg']),
      ('Shipper',p['shipper']), ('Consignee',p['consignee'])
    ]

def create_doc(path, doc_type, doc_id, p, style, overrides=None):
    overrides = overrides or {}
    c=canvas.Canvas(str(path),pagesize=A4)
    title_map={
      'dangerous_goods_declaration':'Dangerous-Goods Declaration - Mock Data Sheet',
      'shipping_details_summary':'Shipping Details Summary - Mock Data Sheet',
      'packing_list':'Packing List - Mock Data Sheet',
      'sds_section_14':'SDS Section 14 - Transport Information Extract'
    }
    W,H=common_page(c,title_map[doc_type],doc_id,p['case_id'],style)
    if doc_type=='dangerous_goods_declaration':
        rows=dg_rows(p, overrides.get('un_number'))
        if style % 2 == 0:
            y=H-62*mm
            y=draw_field_rows(c,rows,y,row_h=12*mm,font_size=8.8)
        else:
            # Two-column compact table with stronger grid variation.
            x0=20*mm; top=H-61*mm; colw=83*mm; gap=5*mm; rh=18*mm
            for i,(label,value) in enumerate(rows):
                col=i%2; row=i//2; x=x0+col*(colw+gap); y=top-row*rh
                c.setFillColor(colors.HexColor('#D9EAF7' if col==0 else '#E8EEF4'))
                c.roundRect(x,y-rh+2*mm,colw,rh-2*mm,2*mm,fill=1,stroke=0)
                c.setFillColor(colors.HexColor('#334E68')); c.setFont('Helvetica-Bold',7.5); c.drawString(x+3*mm,y-5*mm,label.upper())
                wrap_text(c,value,x+3*mm,y-10*mm,colw-6*mm,size=8,leading=9,color=colors.HexColor('#102A43'))
    elif doc_type=='shipping_details_summary':
        values=[('Shipping reference',f'SYN-BL-{p["case_id"][-3:]}'),('Container number',p['container_number']),('Seal number',p['seal_number']),
                ('Shipper',p['shipper']),('Consignee',p['consignee']),('Port of loading',p['port_of_loading']),
                ('Port of discharge',p['port_of_discharge']),('Cargo description',p['commodity_description']),
                ('UN number (declared)',overrides.get('un_number',p['un_number'])),('Hazard class (declared)',overrides.get('hazard_class',p['hazard_class']))]
        if style % 2 == 0:
            y=H-62*mm; y=draw_field_rows(c,values,y,row_h=12*mm,font_size=8.6)
        else:
            x0=20*mm; top=H-60*mm; colw=170*mm; rh=15*mm
            for i,(label,value) in enumerate(values):
                y=top-i*rh
                c.setFillColor(colors.HexColor('#F0F4F8') if i%2==0 else colors.white)
                c.rect(x0,y-rh+2*mm,colw,rh,fill=1,stroke=0)
                c.setFillColor(colors.HexColor('#334E68')); c.setFont('Helvetica-Bold',8.5); c.drawString(x0+3*mm,y-6*mm,label)
                wrap_text(c,value,x0+62*mm,y-6*mm,105*mm,size=8.5,leading=9,color=colors.HexColor('#102A43'))
    elif doc_type=='packing_list':
        seal=overrides.get('seal_number',p['seal_number'])
        rows=[('Packing list reference',f'SYN-PL-{p["case_id"][-3:]}'),('Container number',p['container_number']),('Seal number',seal),
              ('Goods description',p['commodity_description']),('Package count / type',p['packages']),
              ('Gross weight (kg)',p['gross_weight_kg']),('UN number shown',overrides.get('un_number',p['un_number'])),
              ('Hazard class shown',p['hazard_class']),('Consignee',p['consignee'])]
        if style % 2 == 0:
            y=H-62*mm; y=draw_field_rows(c,rows,y,row_h=13*mm,font_size=8.8)
        else:
            # Faux manifest table, not an official layout.
            x=20*mm; y=H-65*mm
            headers=['FIELD','DECLARED VALUE']; widths=[57*mm,113*mm]
            c.setFillColor(colors.HexColor('#243B53')); c.rect(x,y-9*mm,sum(widths),9*mm,fill=1,stroke=0)
            c.setFillColor(colors.white); c.setFont('Helvetica-Bold',8)
            c.drawString(x+3*mm,y-6*mm,headers[0]); c.drawString(x+widths[0]+3*mm,y-6*mm,headers[1])
            y-=9*mm
            for i,(label,value) in enumerate(rows):
                c.setFillColor(colors.HexColor('#F0F4F8') if i%2==0 else colors.white); c.rect(x,y-10*mm,sum(widths),10*mm,fill=1,stroke=0)
                c.setFillColor(colors.HexColor('#334E68')); c.setFont('Helvetica-Bold',8); c.drawString(x+3*mm,y-6*mm,label)
                wrap_text(c,value,x+widths[0]+3*mm,y-6*mm,widths[1]-6*mm,size=8,leading=8)
                y-=10*mm
    elif doc_type=='sds_section_14':
        un=overrides.get('un_number',p['un_number'])
        if un=='UN 3082': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.'; cls='9'; pg='III'
        elif un=='UN 3077': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, SOLID, N.O.S.'; cls='9'; pg='III'
        else: name='CORROSIVE LIQUID, N.O.S.'; cls='8'; pg=p['packing_group']
        vals=[('14.1 UN number or ID number',un),('14.2 UN proper shipping name',name),('14.3 Transport hazard class(es)',cls),
              ('14.4 Packing group (if applicable)',pg),('14.5 Environmental hazards',p['marine_pollutant']),
              ('Product identifier',p['product_identifier']),('Test note','Synthetic excerpt for OCR pipeline testing; not a safety data sheet for a real product.')]
        if style % 2 == 0:
            y=H-61*mm; y=draw_field_rows(c,vals,y,row_h=15*mm,font_size=8.6)
        else:
            x=20*mm; y=H-61*mm
            for label,value in vals:
                c.setFillColor(colors.HexColor('#D9EAF7')); c.roundRect(x,y-9*mm,170*mm,8*mm,1*mm,fill=1,stroke=0)
                c.setFillColor(colors.HexColor('#243B53')); c.setFont('Helvetica-Bold',8.4); c.drawString(x+3*mm,y-6*mm,label)
                y-=11*mm
                y=wrap_text(c,value,x+5*mm,y,162*mm,size=8.5,leading=10,color=colors.HexColor('#102A43'))-4*mm
    draw_footer(c, 20*mm)
    c.save()

# Data plan: one packet has four document types. Two intentional cross-document mismatches are built in.
records=[]
for packet in packets:
    cid=packet['case_id'][-3:]
    specs=[
      ('dangerous_goods_declaration',{},'DG'),
      ('shipping_details_summary',{},'SHIP'),
      ('packing_list',({'seal_number':'SYNSEAL999'} if cid=='002' else {}),'PACK'),
      ('sds_section_14',({'un_number':'UN 3082'} if cid=='003' else {}),'SDS'),
    ]
    for j,(doc_type,ovr,short) in enumerate(specs):
        doc_id=f'{cid}-{short}'
        # DG declaration in case 003 is intentionally made inconsistent with its SDS: set DG to UN 3082.
        effective_overrides=dict(ovr)
        if cid=='003' and doc_type=='dangerous_goods_declaration':
            effective_overrides['un_number']='UN 3082'
        filename=f'{doc_id}_{doc_type}.pdf'
        create_doc(DOCS/filename,doc_type,doc_id,packet,style=(j+int(cid))%2,overrides=effective_overrides)
        fields={}
        # For each file, labels correspond to what appears in that document, not the packet master record.
        if doc_type=='dangerous_goods_declaration':
            fields={'container_number':packet['container_number'],'seal_number':packet['seal_number'],
                    'un_number':effective_overrides.get('un_number',packet['un_number']),
                    'proper_shipping_name': ('ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.' if effective_overrides.get('un_number')=='UN 3082' else ('ENVIRONMENTALLY HAZARDOUS SUBSTANCE, SOLID, N.O.S.' if effective_overrides.get('un_number')=='UN 3077' else packet['proper_shipping_name'])),
                    'hazard_class': ('9' if effective_overrides.get('un_number') in ('UN 3082','UN 3077') else packet['hazard_class']),
                    'packing_group': ('III' if effective_overrides.get('un_number') in ('UN 3082','UN 3077') else packet['packing_group']),
                    'packages':packet['packages'],'gross_weight_kg':packet['gross_weight_kg'],'shipper':packet['shipper'],'consignee':packet['consignee']}
        elif doc_type=='shipping_details_summary':
            fields={'shipping_reference':f'SYN-BL-{cid}','container_number':packet['container_number'],'seal_number':packet['seal_number'],
                    'shipper':packet['shipper'],'consignee':packet['consignee'],'port_of_loading':packet['port_of_loading'],
                    'port_of_discharge':packet['port_of_discharge'],'cargo_description':packet['commodity_description'],
                    'un_number':packet['un_number'],'hazard_class':packet['hazard_class']}
        elif doc_type=='packing_list':
            fields={'packing_list_reference':f'SYN-PL-{cid}','container_number':packet['container_number'],
                    'seal_number':effective_overrides.get('seal_number',packet['seal_number']),'goods_description':packet['commodity_description'],
                    'packages':packet['packages'],'gross_weight_kg':packet['gross_weight_kg'],
                    'un_number':packet['un_number'],'hazard_class':packet['hazard_class'],'consignee':packet['consignee']}
        else:
            u=effective_overrides.get('un_number',packet['un_number'])
            if u=='UN 3082': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.'; cls='9'; pg='III'
            elif u=='UN 3077': name='ENVIRONMENTALLY HAZARDOUS SUBSTANCE, SOLID, N.O.S.'; cls='9'; pg='III'
            else: name='CORROSIVE LIQUID, N.O.S.'; cls='8'; pg=packet['packing_group']
            fields={'un_number':u,'proper_shipping_name':name,'hazard_class':cls,'packing_group':pg,
                    'environmental_hazards':packet['marine_pollutant'],'product_identifier':packet['product_identifier']}
        record={'document_id':doc_id,'case_id':packet['case_id'],'document_type':doc_type,'pdf_path':f'documents/{filename}',
                'clean_image_path':f'images/clean/{doc_id}.png','scan_like_image_path':f'images/scan_like/{doc_id}.png',
                'expected_fields':fields,'synthetic_only':True}
        records.append(record)

# Render each PDF to one page PNG using pdftoppm.
for rec in records:
    pdf=ROOT/rec['pdf_path']
    tmp=ROOT/'_render_tmp'
    tmp.mkdir(exist_ok=True)
    prefix=tmp/rec['document_id']
    subprocess.run(['pdftoppm','-png','-r','170','-singlefile',str(pdf),str(prefix)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    rendered=Path(str(prefix)+'.png')
    clean_path=ROOT/rec['clean_image_path']
    shutil.copyfile(rendered,clean_path)
    # Create mildly degraded grayscale scan-like variant. Seeded for reproducibility.
    random.seed(rec['document_id'])
    im=Image.open(clean_path).convert('L')
    im=ImageEnhance.Contrast(im).enhance(0.88)
    im=im.filter(ImageFilter.GaussianBlur(radius=0.22))
    # low-level paper/scan noise
    import numpy as np
    arr=np.asarray(im).astype('int16')
    noise=np.random.default_rng(sum(ord(ch) for ch in rec['document_id'])).normal(0,1.6,arr.shape)
    arr=np.clip(arr+noise,0,255).astype('uint8')
    sim=Image.fromarray(arr)
    angle=random.uniform(-0.45,0.45)
    sim=sim.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=245)
    sim.save(ROOT/rec['scan_like_image_path'],format='PNG',dpi=(150,150),optimize=True)
    im.close(); sim.close()
shutil.rmtree(ROOT/'_render_tmp',ignore_errors=True)

# Write JSONL and JSON labels.
with open(GT/'labels.json','w',encoding='utf-8') as f:
    json.dump(records,f,indent=2,ensure_ascii=False)
with open(GT/'labels.jsonl','w',encoding='utf-8') as f:
    for r in records: f.write(json.dumps(r,ensure_ascii=False)+'\n')
# CSV is useful for annotation/inspection; fields are unioned across documents.
all_fields=sorted(set(k for r in records for k in r['expected_fields']))
with open(GT/'field_ground_truth.csv','w',newline='',encoding='utf-8-sig') as f:
    cols=['document_id','case_id','document_type','pdf_path','clean_image_path','scan_like_image_path']+all_fields
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for r in records:
        row={k:'' for k in cols}
        row.update({k:r[k] for k in ['document_id','case_id','document_type','pdf_path','clean_image_path','scan_like_image_path']})
        row.update(r['expected_fields']); w.writerow(row)
with open(GT/'document_manifest.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=['document_id','case_id','document_type','pdf_path','clean_image_path','scan_like_image_path','field_count','synthetic_only'])
    w.writeheader()
    for r in records:
        w.writerow({'document_id':r['document_id'],'case_id':r['case_id'],'document_type':r['document_type'],
                    'pdf_path':r['pdf_path'],'clean_image_path':r['clean_image_path'],'scan_like_image_path':r['scan_like_image_path'],
                    'field_count':len(r['expected_fields']),'synthetic_only':True})

# Mismatch annotations for future consistency checks.
case_notes=[
 {'case_id':'SYN-CASE-001','expected_cross_document_status':'consistent','intentional_mismatches':[],'note':'All document fields intended to align.'},
 {'case_id':'SYN-CASE-002','expected_cross_document_status':'mismatch','intentional_mismatches':[{'field':'seal_number','document_a':'dangerous_goods_declaration','value_a':'SYNSEAL002','document_b':'packing_list','value_b':'SYNSEAL999'}],'note':'The packing list seal is intentionally different.'},
 {'case_id':'SYN-CASE-003','expected_cross_document_status':'mismatch','intentional_mismatches':[{'field':'un_number','document_a':'dangerous_goods_declaration','value_a':'UN 3082','document_b':'sds_section_14','value_b':'UN 3082'}],'note':'DG declaration content uses UN 3082; SDS is also overridden to UN 3082 to ensure document-level labels. The packet-master commodity suggests UN 3077, so use this as a document consistency fixture only, not a chemistry example.'}
]
# Correct case 3 notes to explicitly state the present mismatch across the shipping summary/packing list and SDS isn't packet-master semantics.
case_notes[-1]['intentional_mismatches']=[{'field':'un_number','document_a':'shipping_details_summary','value_a':'UN 3077','document_b':'dangerous_goods_declaration','value_b':'UN 3082'}]
with open(GT/'case_level_test_notes.json','w',encoding='utf-8') as f: json.dump(case_notes,f,indent=2)

# Evaluation script. Predictions JSON: list of {document_id, fields:{field: value}} or JSONL same per line.
eval_script=r'''#!/usr/bin/env python3
"""Evaluate extracted field values against PortGuard synthetic ground truth.

Usage:
  python scripts/evaluate_field_extraction.py predictions.json

Accepted predictions format is a JSON array or JSONL records such as:
  {"document_id":"001-DG","fields":{"container_number":"DEMU1234560","un_number":"UN 1760"}}
Only fields present in each document's ground truth are scored.
"""
import json, sys, re, unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
GT=json.loads((ROOT/'ground_truth'/'labels.json').read_text(encoding='utf-8'))

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
'''
(ROOT/'scripts'/'evaluate_field_extraction.py').write_text(eval_script,encoding='utf-8')

readme='''# PortGuard OCR + Document Extraction Starter Dataset\n\n**Purpose:** starter material for building and testing OCR and field extraction in the PortGuard academic prototype.\n\n## Important data notice\n- Every record and document in this package is synthetic and labelled **SYNTHETIC - TEST ONLY**.\n- These are mock data sheets inspired by common document categories, not copies of official customs, carrier, dangerous-goods or SDS forms.\n- They are not evidence of regulatory compliance and must not be used for real shipping, customs, safety or operational decisions.\n- Synthetic examples are useful for pipeline development and software tests; they do not prove performance on real port documents.\n\n## Contents\n- `documents/`: 12 one-page mock PDFs: 3 linked test cases x 4 document types.\n- `images/clean/`: clean page renders of each PDF (use as OCR inputs).\n- `images/scan_like/`: mildly degraded grayscale versions to test OCR robustness. These are generated degradations, not real scanner captures.\n- `ground_truth/labels.json`: complete labels with expected fields for each document.\n- `ground_truth/labels.jsonl`: one JSON object per line, useful for streaming pipelines.\n- `ground_truth/field_ground_truth.csv`: flat field-level labels for viewing/annotation.\n- `ground_truth/document_manifest.csv`: path and document-type index.\n- `ground_truth/case_level_test_notes.json`: notes on intentional cross-document mismatches for later consistency-check testing.\n- `scripts/evaluate_field_extraction.py`: exact-match field evaluation helper.\n\n## Document types and fields\n1. `dangerous_goods_declaration`: container number, seal number, UN number, proper shipping name, hazard class, packing group, packages, gross weight, shipper and consignee.\n2. `shipping_details_summary`: shipping reference, container and seal numbers, shipper, consignee, ports, cargo description, UN number and hazard class.\n3. `packing_list`: reference, container and seal numbers, goods description, packages, gross weight, UN number, hazard class and consignee.\n4. `sds_section_14`: UN number, proper shipping name, transport hazard class, packing group, environmental-hazard note and product identifier.\n\nField values are document-specific: labels reflect what actually appears on that synthetic document, including any intentional mismatch. Do not substitute case-master values for per-document ground truth.\n\n## Suggested first experiment\n1. Run your OCR engine against every image under `images/clean/`.\n2. Store OCR text per `document_id`.\n3. Add document-type-specific extraction that emits JSON using the field names in `ground_truth/labels.json`.\n4. Save model outputs in a JSON file/JSONL as records like:\n\n```json\n{\"document_id\": \"001-DG\", \"fields\": {\"container_number\": \"DEMU1234560\", \"un_number\": \"UN 1760\"}}\n```\n\n5. Evaluate using:\n\n```bash\npython scripts/evaluate_field_extraction.py predictions.json\n```\n\n6. Repeat with `images/scan_like/` and compare performance. Treat the 12 documents as a small smoke-test set, not a statistically sufficient benchmark.\n\n## Notes for interpretation\n- Exact-match field accuracy is a simple starter metric. It does not replace character error rate (CER), word error rate (WER), per-field precision/recall/F1, or manual review of safety-critical fields.\n- Missing, unreadable or uncertain values should be returned as null/unknown by the application rather than invented.\n- A real-world evaluation needs authorised, appropriately redacted samples and independently checked labels from a domain expert.\n'''
(ROOT/'README.md').write_text(readme,encoding='utf-8')

# Generate a concise summary / counts.
summary={'document_count':len(records),'case_count':len(packets),'pdf_count':len(list(DOCS.glob('*.pdf'))),
         'clean_image_count':len(list(CLEAN.glob('*.png'))),'scan_like_image_count':len(list(SCAN.glob('*.png'))),
         'document_types':sorted(set(r['document_type'] for r in records)),
         'ground_truth_field_count':sum(len(r['expected_fields']) for r in records)}
(ROOT/'DATASET_SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
