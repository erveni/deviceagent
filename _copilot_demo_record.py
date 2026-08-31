import subprocess, time, sys
sys.path.insert(0, '/Users/seolocalph/projects/device-agent')
from copilot_edge_probe import sh, dump, find, tap, dismiss_fre, top_activity

S = 'adb-R83L112EVWK-PydBnX._adb-tls-connect._tcp'
PKG = 'com.microsoft.emmx'
REMOTE = '/sdcard/copilot_demo.mp4'

sh(S, f'shell pm clear {PKG}', 60)
sh(S, f'shell rm -f {REMOTE}', 15)
sh(S, 'shell input keyevent KEYCODE_HOME', 10)
time.sleep(1)

rec = subprocess.Popen(f'adb -s "{S}" shell screenrecord --time-limit 180 --bit-rate 8000000 {REMOTE}',
                       shell=True)
time.sleep(3)
t0 = time.time()

sh(S, f'shell monkey -p {PKG} -c android.intent.category.LAUNCHER 1', 30)
time.sleep(7)
print('fre:', dismiss_fre(S), top_activity(S), f'{time.time()-t0:.0f}s', flush=True)

btn = find(dump(S), id_='edge_location_bar_copilot_button')
tap(S, btn, 6)
box = find(dump(S), cls='EditText')
tap(S, box, 2)
sh(S, "shell input text 'best%splumber%snear%sme'", 30)
time.sleep(2)
send = find(dump(S), desc='Send')
print('send node:', bool(send), f'{time.time()-t0:.0f}s', flush=True)
tap(S, send, 5)

# let the answer stream, then hold on it so the video shows the finished response
for _ in range(14):
    nodes = dump(S)
    if any(len(n['text']) > 60 for n in nodes):
        break
    time.sleep(4)
time.sleep(6)
print('answered', f'{time.time()-t0:.0f}s', flush=True)

# scroll the answer, then follow the citation to prove the backlink resolves
sh(S, 'shell input swipe 360 1100 360 700 400', 15)
time.sleep(4)
cit = find(dump(S), desc='Link from')
print('citation:', cit['desc'] if cit else None, f'{time.time()-t0:.0f}s', flush=True)
if cit:
    tap(S, cit, 10)
    print('landed:', top_activity(S), flush=True)
    time.sleep(6)

sh(S, 'shell pkill -INT screenrecord', 15)
rec.wait(timeout=60)
time.sleep(3)
print('remote size:', sh(S, f'shell ls -la {REMOTE}', 15).stdout.strip(), flush=True)
