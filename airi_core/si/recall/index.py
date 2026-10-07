import re

def init(c):
    c.execute('CREATE VIRTUAL TABLE IF NOT EXISTS recall USING fts5(source_id UNINDEXED,source_date UNINDEXED,text,tokenize="unicode61")')

def update(c,records):
    count=0
    for row in records:
        sid='chat:'+str(row['id'])
        if c.execute('SELECT 1 FROM recall WHERE source_id=?',(sid,)).fetchone():continue
        c.execute('INSERT INTO recall(source_id,source_date,text) VALUES(?,?,?)',(sid,str(row['created']),str(row['content'])[:12000]));count+=1
    return count

def search(c,query,limit=5):
    words=re.findall(r'[\w가-힣]{2,}',query)[:12]
    if not words:return []
    match=' OR '.join('"'+x.replace('"','""')+'"' for x in words)
    return [dict(r) for r in c.execute('SELECT source_id,source_date,snippet(recall,2,\'\',\'\',\'…\',32) AS excerpt,bm25(recall) AS rank FROM recall WHERE recall MATCH ? ORDER BY rank LIMIT ?',(match,min(10,max(1,limit))))]
