"""Read whole tabular attachments locally; never ask an LLM to calculate from a prefix."""
import csv,io,json,re,collections,statistics
from pathlib import Path

def number(text):
    try:
        value=float(str(text).replace(',',''))
        return value if __import__('math').isfinite(value) else None
    except (ValueError,TypeError):return None

def read_table(path):
    path=Path(path)
    if path.suffix.lower() in ('.csv','.tsv'):
        raw=path.read_bytes()
        for encoding in ('utf-8-sig','cp949'):
            try:text=raw.decode(encoding);break
            except UnicodeDecodeError:pass
        else:raise ValueError('CSV 문자 인코딩을 확인해 주세요.')
        source=csv.reader(io.StringIO(text),delimiter='\t' if path.suffix.lower()=='.tsv' else ',')
    elif path.suffix.lower()=='.xlsx':
        import openpyxl
        wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
        if len(wb.worksheets)!=1:raise ValueError('여러 시트의 분석은 시트별 CSV로 첨부해 주세요. 일부 시트를 전체로 분석하지 않습니다.')
        source=wb.active.iter_rows(values_only=True)
    elif path.suffix.lower()=='.xls':
        import xlrd
        wb=xlrd.open_workbook(path)
        if wb.nsheets!=1:raise ValueError('여러 시트는 CSV로 나눠 주세요.')
        sheet=wb.sheet_by_index(0);source=(sheet.row_values(i) for i in range(sheet.nrows))
    else:raise ValueError('표 분석은 CSV, TSV, XLSX, XLS를 지원합니다.')
    source=iter(source);rawheaders=next(source,None)
    if not rawheaders:raise ValueError('비어 있는 표입니다.')
    headers=[]
    for i,h in enumerate(rawheaders):
        name=str(h or '').strip() or 'unnamed_'+str(i+1)
        if name in headers:name+='_'+str(i+1)
        headers.append(name)
    records=[]
    for row in source:
        if len(records)>=250000:raise ValueError('25만 행을 초과합니다. 파일을 나눠 주세요.')
        if len(row)>len(headers) and any(v not in ('',None) for v in row[len(headers):]):raise ValueError('열 개수가 맞지 않는 행이 있습니다. 원본 CSV 구분자를 확인해 주세요.')
        records.append({h:str(row[i]).strip() if i<len(row) and row[i] is not None else '' for i,h in enumerate(headers)})
    return headers,records

def analyze(path,name):
    headers,records=read_table(path)
    lines=['# 전체 데이터 분석','', '원본: '+name,'',f'원본 전체 {len(records):,}행, {len(headers)}열을 로컬에서 읽었습니다. 앞부분 발췌를 사용하지 않았습니다.','', '## 데이터 품질']
    duplicate=len(records)-len({tuple(r.values()) for r in records})
    lines.append(f'- 완전히 동일한 중복 행: {duplicate:,}개. 원본을 임의로 제거하지 않았습니다.')
    for h in headers:
        missing=sum(not r[h] for r in records)
        if missing:lines.append(f'- {h}: 빈 값 {missing:,}개')
    profile=[]
    for h in headers:
        values=[number(r[h]) for r in records];numeric=[v for v in values if v is not None]
        profile.append({'column':h,'rows':len(records),'numeric_count':len(numeric),'missing_count':sum(not r[h] for r in records),'min':min(numeric) if numeric else None,'max':max(numeric) if numeric else None})
    outputs={'column-profile.csv':profile}
    required={'year','industry_code_ANZSIC','industry_name_ANZSIC','rme_size_grp','variable','value','unit'}
    if required.issubset(headers):
        normalized=[]
        for r in records:
            normalized.append({**r,'numeric_value':number(r['value']),'value_status':'numeric' if number(r['value']) is not None else 'unavailable:'+r['value']})
        outputs['transformed-data.csv']=normalized
        years=sorted({r['year'] for r in records},key=lambda x:int(x));latest=years[-1];previous=years[-2] if len(years)>1 else None
        unavailable=collections.Counter(r['value'] for r in records if number(r['value']) is None)
        lines += [f'- 기간: {years[0]}–{latest}. 최신 연도 {latest}년을 주요 비교 기준으로 사용했습니다.',f'- 숫자가 아닌 값: {dict(unavailable)}. 0으로 바꾸지 않고 결측으로 유지했습니다.', '- 이름 없는 원본 열은 unnamed 이름으로 보존했습니다. 추가 열의 값을 주 지표에 합산하지 않았습니다.', '', '## 최신 연도 KPI','', '| 지표 | '+latest+' | '+str(previous or '이전 연도 없음')+' | 전년 대비 | 원본 단위 |','|---|---:|---:|---:|---|']
        totals={(r['year'],r['variable']):r for r in records if r['rme_size_grp']=='j_Grand_Total' and r['industry_code_ANZSIC']=='all'}
        def pct(a,b):return f'{(a/b-1)*100:.2f}%' if a is not None and b not in (None,0) else '계산 불가'
        def fmt(v):return f'{v:,.2f}'.rstrip('0').rstrip('.') if v is not None else '결측'
        for variable in sorted({v for y,v in totals}):
            row=totals.get((latest,variable));prev=totals.get((previous,variable))
            if not row:continue
            a=number(row['value']);b=number(prev['value']) if prev else None
            lines.append(f"| {variable} | {fmt(a)} | {fmt(b)} | {pct(a,b)} | {row['unit']} |")
        def total(year,var):return number(totals.get((year,var),{}).get('value'))
        income=total(latest,'Total income');profit=total(latest,'Operating profit before tax')
        lines+=['',f"세전영업이익 / 총수입 비율: {profit/income*100:.2f}%." if income and profit is not None else '이익 비율 계산에 필요한 값이 없습니다.', '', '단위 DOLLARS(millions)는 백만 달러입니다. 억 달러로 바꾸지 않았으며, CSV만으로 통화 코드를 단정하지 않습니다. 총수입−총지출과 공표 영업이익이 같다고 가정하지 않습니다.']
        groups=collections.defaultdict(dict)
        for r in records:
            if r['rme_size_grp']=='i_Industry_Total':groups[(r['year'],r['industry_code_ANZSIC'],r['industry_name_ANZSIC'])][r['variable']]=number(r['value'])
        sector=[]
        for (year,code,label),values in groups.items():
            if year!=latest:continue
            prev=groups.get((previous,code,label),{});inc=values.get('Total income');pr=values.get('Operating profit before tax');pinc=prev.get('Total income')
            sector.append({'year':year,'industry':label,'income_millions':inc,'profit_millions':pr,'income_yoy_pct':(inc/pinc-1)*100 if inc is not None and pinc not in (None,0) else None,'profit_to_income_pct':pr/inc*100 if pr is not None and inc not in (None,0) else None})
        sector.sort(key=lambda r:r['income_millions'] if r['income_millions'] is not None else -float('inf'),reverse=True)
        outputs['industry-kpi.csv']=sector
        lines+=['','## 산업별 비교','산업 합계 행만 사용했습니다. 규모 구간과 산업 합계·전체 합계를 함께 더하지 않았습니다.','','| 산업 | 총수입 백만 달러 | 수입 전년 대비 | 세전영업이익/총수입 |','|---|---:|---:|---:|']
        for r in sector:lines.append(f"| {r['industry']} | {fmt(r['income_millions'])} | {fmt(r['income_yoy_pct'])+'%' if r['income_yoy_pct'] is not None else '결측'} | {fmt(r['profit_to_income_pct'])+'%' if r['profit_to_income_pct'] is not None else '결측'} |")
        outputs['annual-totals.csv']=[r for r in normalized if r['rme_size_grp']=='j_Grand_Total' and r['industry_code_ANZSIC']=='all']
        lines+=['','## 사업 전략 검토','이 자료는 산업별 집계입니다. 개별 기업의 고객, 원가, 현금흐름이나 목표 시장을 제공하지 않으므로 아래는 검증할 전략 가설입니다.','- 자기 업종의 수입 성장률과 이익 비율을 기업 실적과 비교해, 시장 성장 부족과 내부 수익성 문제를 구분합니다.','- 수입이 늘어도 이익 비율이 낮아지는 업종은 가격·원가·제품 구성을 먼저 점검합니다. 업종 성장만으로 투자 확대를 결정하지 않습니다.','- 규모 구간별 비교는 산업 합계와 분리합니다. 기업당 매출 및 종업원당 매출은 COUNT와 백만 달러의 단위를 맞춰 추가 계산합니다.','- 실행 KPI: 매출 성장률, 세전영업이익/매출, 고객 유지율, 현금 전환 주기. 뒤의 두 지표는 회사 내부 데이터가 추가로 필요합니다.']
    else:
        outputs['transformed-data.csv']=records
        lines+=['','## 열별 수치 범위','서로 다른 단위·기간·합계 행을 섞지 않기 위해 전체 숫자 열을 무조건 합산하지 않았습니다.','','| 열 | 숫자 개수 | 최솟값 | 최댓값 |','|---|---:|---:|---:|']
        for p in profile:lines.append(f"| {p['column']} | {p['numeric_count']} | {p['min']} | {p['max']} |")
        lines+=['','정확한 KPI 산출에는 날짜·금액·분류 열과 원하는 집계 기준을 작업 지시에 적어 주세요. 이 결과는 전체 표의 데이터 품질과 기초 통계입니다.']
    # Put the answer before the detailed quality appendix.
    if required.issubset(headers):
        start=lines.index('## 데이터 품질');end=lines.index('## 최신 연도 KPI')
        quality=lines[start:end];lines=lines[:start]+lines[end:]+['','## 데이터 품질 및 처리 범위']+quality[1:]
    return '\n'.join(lines),outputs

def save_outputs(folder,report,outputs):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    (folder/'report.md').write_text(report,encoding='utf-8');(folder/'report.md').chmod(0o600)
    for name,rows in outputs.items():
        if not rows:continue
        with (folder/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
            for row in rows:
                writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','@')) else v) for k,v in row.items()})
        (folder/name).chmod(0o600)

if __name__=='__main__':
    import sys
    report,outputs=analyze(sys.argv[1],sys.argv[2]);save_outputs(sys.argv[3],report,outputs)
    print(json.dumps({'report':report,'files':['report.md',*outputs]},ensure_ascii=False))
