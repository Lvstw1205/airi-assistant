"""Full-table analysis artifacts and authenticated task result metadata."""
import json,re,subprocess
from pathlib import Path

NAMES={'report.md','column-profile.csv','transformed-data.csv','industry-kpi.csv','annual-totals.csv'}
def analyze_tables(app,task):
    reports=[]
    for key in json.loads(task.get('attachment_ids','[]')):
        if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('잘못된 첨부 ID')
        records=app.rows('SELECT name FROM attachments WHERE id=?',(key,))
        if not records:continue
        name=records[0]['name'];ext=Path(name).suffix.lower()
        if ext not in ('.csv','.tsv','.xlsx','.xls'):continue
        folder=app.DATA/'task-results'/str(task['id'])/key
        result=subprocess.run([str(app.ROOT/'.venv/bin/python'),str(app.ROOT/'tabular.py'),str(app.DATA/'attachments'/(key+ext)),name,str(folder)],capture_output=True,text=True,timeout=60)
        if result.returncode:raise ValueError('전체 표 분석 실패. 파일 형식·시트 수를 확인해 주세요. 원본 일부를 전체 결과로 처리하지 않았습니다.')
        reports.append(json.loads(result.stdout)['report'])
    return reports

def files(app,task_id):
    folder=app.DATA/'task-results'/str(task_id)
    if not folder.is_dir():return []
    return [{'key':child.name+'/'+p.name,'name':p.name,'size':p.stat().st_size} for child in sorted(folder.iterdir()) if re.fullmatch('[a-f0-9]{32}',child.name) and child.is_dir() for p in sorted(child.iterdir()) if p.name in NAMES and p.is_file()]
