"""Opt-in download of pinned public models; verifies SHA-256 before installation."""
import hashlib,json,os,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 manifest=json.loads((ROOT/'config/vision-assets.json').read_text())
 for name,entry in manifest['assets'].items():
  path=ROOT/name
  if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']:continue
  print('Downloading',name,flush=True)
  with urllib.request.urlopen(entry['url'],timeout=120) as r:raw=r.read(60*1024*1024)
  if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise RuntimeError('Checksum mismatch: '+name)
  path.parent.mkdir(parents=True,exist_ok=True)
  temp=path.with_suffix(path.suffix+'.download');temp.write_bytes(raw);os.replace(temp,path)
 print('Face and hand models are ready. Camera frames stay on this device.')
if __name__=='__main__':main()
