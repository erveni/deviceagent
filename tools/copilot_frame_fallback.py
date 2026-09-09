"""Recover a missing native screenshot from the same already-framed answer."""
import subprocess


def capture_missing(serial,response,get_current,capture=None):
    if '149145555W002883' not in serial:return None
    block=(response.get('platforms') or {}).get('copilot',{})
    if (block.get('screenshot_b64') or block.get('screenshot_path') or block.get('error')
            or not block.get('response_text') or not block.get('ranking_position')
            or not any('[copilot] frame_shot OK' in s for s in response.get('step_log',[]))):return None
    current=get_current()
    other=(current.get('platforms') or {}).get('copilot',{})
    if current.get('running') or current.get('prompt')!=response.get('prompt'):
        return None
    if any(other.get(k)!=block.get(k) for k in ('response_text','ranking_position','ranking_total')):
        return None
    if capture is None:
        capture=lambda:subprocess.run(['adb','-s',serial,'exec-out','screencap','-p'],capture_output=True,timeout=15).stdout
    png=capture()
    return png if png.startswith(b'\x89PNG\r\n\x1a\n') else None
