#!/usr/bin/env python3
"""Start the source-available AIRI application with a fresh, isolated data folder."""
import argparse,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser(description='AIRI community assistant')
 p.add_argument('--port',type=int,default=8766)
 p.add_argument('--data-dir',type=Path,default=ROOT/'data')
 p.add_argument('--standby',action='store_true',help='Smoke-test mode; no background jobs')
 p.add_argument('--device-worker',action='store_true',help='Share this computer for paired AI inference only')
 p.add_argument('--listen',help='Worker private IP; automatically detected when omitted')
 p.add_argument('--worker-port',type=int,default=8770)
 p.add_argument('--device-name',default='추가 기기')
 p.add_argument('--rotate-pairing',action='store_true',help='Revoke old worker connection codes')
 args=p.parse_args()
 if not 1024<=args.port<=65535:p.error('Port must be between 1024 and 65535')
 os.chdir(ROOT);os.environ['AIRI_PORT']=str(args.port);os.environ['AIRI_DATA']=str(args.data_dir.resolve())
 if args.device_worker:
  if not 1024<=args.worker_port<=65535:p.error('Worker port must be between 1024 and 65535')
  from device_transport import run_worker
  run_worker(args.data_dir.resolve()/'device-worker',args.listen,args.worker_port,args.device_name,args.rotate_pairing)
  return
 if args.standby:os.environ['AIRI_STANDBY']='1'
 import server
 server.main()
if __name__=='__main__':main()
