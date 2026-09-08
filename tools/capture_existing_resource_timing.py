"""Read existing Gemini resource timings after a job. Never navigate or fetch assets."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gemini_cdp_capture import CDP

parser = argparse.ArgumentParser()
parser.add_argument('serial')
parser.add_argument('output', type=Path)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit('Output already exists')
if any(Path(p.strip()).name == 'gost' for p in subprocess.check_output(
        ['ps', '-axo', 'comm='], text=True).splitlines()):
    raise SystemExit('Proxy still active; wait for teardown')
def adb(*cmd):
    return subprocess.check_output(['adb', '-s', args.serial, *cmd], timeout=20)
sockets = set(re.findall(r'@(chrome_devtools_remote[^\s]*)',
                         adb('shell', 'cat', '/proc/net/unix').decode()))
result = None
for socket in sorted(sockets, reverse=True):
    port = int(adb('forward', 'tcp:0', 'localabstract:'+socket).strip())
    client = None
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=3) as response:
            tabs = json.load(response)
        pages = [t for t in tabs if t.get('type') == 'page'
                 and t.get('url', '').startswith('https://gemini.google.com/')]
        if len(pages) != 1:
            continue
        client = CDP(pages[0]['webSocketDebuggerUrl'])
        result = client.call('Runtime.evaluate', {'returnByValue': True, 'expression': r'''(()=>({
          timeOrigin:performance.timeOrigin,
          resources:performance.getEntriesByType('resource').map(e=>{
            const u=new URL(e.name);return {host:u.hostname,path:u.pathname,
              initiatorType:e.initiatorType,startTime:e.startTime,duration:e.duration,
              transferSize:e.transferSize,encodedBodySize:e.encodedBodySize,
              decodedBodySize:e.decodedBodySize}})
        }))()'''})['result']['result']['value']
        break
    except Exception as exc:
        print('Read unavailable:', type(exc).__name__)
    finally:
        if client:
            client.close()
        adb('forward', '--remove', f'tcp:{port}')
if result is None:
    raise SystemExit('No unique readable existing Gemini page')
result['limitations'] = ['Existing performance buffer may omit early requests.',
                         'Cross-origin timing restrictions can hide byte sizes.',
                         'Not an Evomi billing ledger; no resource was re-fetched.']
args.output.write_text(json.dumps(result, indent=2)+'\n')
print('Saved', len(result['resources']), 'existing resource entries')
for item in sorted(result['resources'], key=lambda r:r['transferSize'], reverse=True)[:15]:
    print(json.dumps(item))
