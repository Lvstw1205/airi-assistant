"""Same-date same-unit cross checks; FRED is a republication, not independent news."""
import csv,io,datetime as dt,urllib.request

def fred(series):
 url='https://fred.stlouisfed.org/graph/?g=download'  # provenance uses canonical series below
 data_url='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+series
 with urllib.request.urlopen(urllib.request.Request(data_url,headers={'User-Agent':'AIRI-Research/1.0'}),timeout=10) as response:raw=response.read(1000000).decode()
 out={}
 for row in csv.DictReader(io.StringIO(raw)):
  try:out[row.get('observation_date') or row.get('DATE')]=float(row[series])
  except (KeyError,ValueError):continue
 return out,'https://fred.stlouisfed.org/series/'+series

def compare(rows,loader=fred):
 result=[]
 for row in rows:
  series={'us2y':'DGS2','us10y':'DGS10'}.get(row['symbol'])
  if not series:continue
  item={'instrument_id':row['instrument_id'],'primary_value':row.get('value'),'primary_url':row.get('source_url'),'primary_provider':row['provider'],'unit':'percent','status':'unavailable','note':'FRED 재배포 경로 비교이며 독립 원천으로 세지 않는다'};result.append(item)
  try:
   values,url=loader(series);day=row['history'][-1]['date'];item.update(date=day,secondary_url=url,secondary_provider='FRED',retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
   if day not in values:item['reason']='동일 날짜 없음';continue
   other=values[day];difference=abs(other-row['value'])*100;item.update(secondary_value=other,difference_bp=difference,threshold_bp=1,status='conflict' if difference>=1-1e-9 else 'matched')
  except Exception as e:item['reason']=type(e).__name__
 return result
