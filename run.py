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
 args=p.parse_args()
 if not 1024<=args.port<=65535:p.error('Port must be between 1024 and 65535')
 os.chdir(ROOT);os.environ['AIRI_PORT']=str(args.port);os.environ['AIRI_DATA']=str(args.data_dir.resolve())
 if args.standby:os.environ['AIRI_STANDBY']='1'
 import server
 server.main()
if __name__=='__main__':main()
