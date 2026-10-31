"""Lossless source inventory and read-only XLSX import; Python standard library only."""
from pathlib import Path
import zipfile, xml.etree.ElementTree as ET, json, re, hashlib, difflib
ROOT = Path(__file__).resolve().parents[1]
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def workbook(path):
    with zipfile.ZipFile(path) as z:
        strings = [''.join(t.text or '' for t in si.findall('.//s:t', NS)) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        sheets = ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets', NS)
        result = {}
        for i, sheet in enumerate(sheets, 1):
            rows=[]
            for row in ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')).findall('.//s:row', NS):
                cells={}
                for cell in row:
                    v=cell.find('s:v', NS)
                    value=v.text if v is not None else ''
                    if cell.get('t')=='s': value=strings[int(value)]
                    elif cell.get('t')=='inlineStr': value=''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                    cells[re.sub(r'\d+', '', cell.get('r'))]={'value':value, 'formula':cell.find('s:f', NS).text if cell.find('s:f', NS) is not None else None}
                rows.append({'row':int(row.get('r')), 'cells':cells})
            result[sheet.get('name')]=rows
        return result

def main():
    raw=workbook(ROOT/'AI_Takeoff_Master_Table.xlsx')
    val=lambda r,c:r['cells'].get(c,{}).get('value','')
    fields={val(r,'A'):val(r,'B') for r in raw['Field Table'][1:]}
    markdown=[]
    for p in sorted((ROOT/'Field of Study').glob('*.md')):
        text=p.read_text()
        markdown.append({'path':str(p.relative_to(ROOT)), 'sha256':digest(p), 'text':text, 'links':sorted(set(re.findall(r'https?://[^\s)\]>]+',text)))})
    norm=lambda s:re.sub('[^a-z]','',s.lower())
    byname={norm(Path(d['path']).stem.removeprefix('v2_')):d for d in markdown}
    entries=[]
    for r in raw['Master Table'][1:]:
        id=val(r,'A')
        if not id: continue
        field=fields.get(id.split('-')[0],val(r,'B'))
        key=norm(field)
        if key not in byname:
            matches=difflib.get_close_matches(key,byname,n=1,cutoff=.75)
            key=matches[0] if matches else None
        doc=byname.get(key)
        entries.append({'id':id,'field':field,'title':val(r,'D'),'description':val(r,'E'),'impact':val(r,'F'), 'duplicate':val(r,'H'),'forecast':{'year':val(r,'I'),'confidence':val(r,'J'),'rationale':val(r,'L'),'status':'draft-unverified'},'rawPrerequisites':val(r,'K'),'category':val(r,'M'),'review':'unreviewed','provenance':{'workbook':'AI_Takeoff_Master_Table.xlsx','sheet':'Master Table','row':r['row'],'markdown':doc['path'] if doc else None,'markdownMapping':'filename match' if doc and norm(field)==key else 'approximate filename match — inspect original','markdownSha256':doc['sha256'] if doc else None}, 'sourceLinks':doc['links'] if doc else []})
    ids={e['id'] for e in entries};lookup={e['id']:e for e in entries}
    relationships=[]
    # Known wrong ID/name pairs are recorded, never silently remapped.
    known={'NEU-01':'Aging pathway mapping','GEN-01':'Epigenetic reprogramming','BIO-01':'Senescent cell elimination'}
    for r in raw['Prerequisites Map'][1:]:
        down,up=val(r,'A'),val(r,'D')
        if not down and not up: continue
        issues=[]
        if up not in ids: issues.append('missing-upstream')
        if down not in ids: issues.append('missing-downstream')
        if up in known and any(t in val(r,'E').lower() for t in ['aging','epigenetic','senescen']): issues.append('confirmed-id-name-mismatch')
        # Lexical warnings are review aids, not automatic semantic judgments.
        if up in ids and not set(re.findall(r'[a-z]{4,}',val(r,'E').lower())) & set(re.findall(r'[a-z]{4,}',lookup[up]['title'].lower())): issues.append('name-review-needed')
        relationships.append({'id':f'raw-edge-{r["row"]}', 'from':up,'to':down,'rawType':val(r,'F'),'upstreamLabel':val(r,'E'),'downstreamLabel':val(r,'B'),'notes':val(r,'H'),'review':'quarantined','issues':issues,'actualUpstreamTitle':lookup.get(up,{}).get('title'),'provenance':{'workbook':'AI_Takeoff_Master_Table.xlsx','sheet':'Prerequisites Map','row':r['row']}})
    manifests=[]
    for name in ['_discoveries_manifest.json','_v2_manifest.json']:
        data=json.loads((ROOT/name).read_text())
        manifests.append({'path':name,'sha256':digest(ROOT/name),'original':data,'missingRecordedPaths':sum(not Path(x.get('filePath','')).is_file() for x in data)})
    audit={'entries':len(entries),'markdownFiles':len(markdown),'uniqueIds':len(ids),'relationships':len(relationships),'relationshipTypes':{t:sum(e['rawType']==t for e in relationships) for t in ['HARD','SOFT','ENABLES']},'missingUpstreamRows':sum('missing-upstream' in e['issues'] for e in relationships),'missingUpstreamIds':sorted({e['from'] for e in relationships if 'missing-upstream' in e['issues']}),'missingDownstreamRows':sum('missing-downstream' in e['issues'] for e in relationships),'confirmedMismatchRows':sum('confirmed-id-name-mismatch' in e['issues'] for e in relationships),'nameReviewRows':sum('name-review-needed' in e['issues'] for e in relationships),'policy':'All imported links quarantined; lexical warnings are not a complete semantic audit.'}
    out={'schemaVersion':1,'workbookSha256':digest(ROOT/'AI_Takeoff_Master_Table.xlsx'),'entries':entries,'relationships':relationships,'markdown':markdown,'manifests':manifests,'rawWorkbook':raw,'audit':audit}
    (ROOT/'research/imported.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k!='missingUpstreamIds'},indent=2))
if __name__=='__main__': main()
