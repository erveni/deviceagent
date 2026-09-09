"""Read-only API snapshot for an explicit daily plan; no device/proxy actions."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import urllib.request
import ssl
import certifi
import time


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--base',default='https://jjm59vpn3y.us-east-1.awsapprunner.com')
    args=parser.parse_args();args.output.mkdir(exist_ok=False)
    secret=json.loads(subprocess.check_output(['aws','secretsmanager','get-secret-value',
        '--secret-id','aeo-admin/prod','--profile','aeo-admin','--region','us-east-1',
        '--query','SecretString','--output','text'],stderr=subprocess.PIPE))
    headers={'X-Executor-Token':secret['EXECUTOR_TOKEN']}
    if secret.get('READ_API_TOKEN'):headers['Authorization']='Bearer '+secret['READ_API_TOKEN']
    request=urllib.request.Request(args.base.rstrip('/')+'/api/llm/daily-catalog',headers=headers)
    with urllib.request.urlopen(request,timeout=45,context=ssl.create_default_context(cafile=certifi.where())) as response:
        catalog=json.load(response)
    if catalog.get('version') != 'daily-guide-v1':
        raise ValueError('Deploy the daily-guide-v1 catalog before planning')
    counts={}
    for endpoint,filename in [('businesses','biz_admin.json'),('keywords','kw_admin.json'),('clients','clients_admin.json')]:
        data=catalog[endpoint]
        if not isinstance(data,list):raise ValueError('Catalog response is not a list: '+endpoint)
        with (args.output/filename).open('x') as stream:json.dump(data,stream)
        (args.output/filename).chmod(0o600)
        counts[endpoint]=len(data)
    with (args.output/'snapshot.json').open('x') as stream:
        json.dump(dict(at=datetime.now(timezone.utc).isoformat(),read_only=True,counts=counts),stream,indent=2)
    print(json.dumps(dict(output=str(args.output),counts=counts)))


if __name__=='__main__':main()
