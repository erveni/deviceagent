"""Drive Microsoft Edge + Copilot on one phone over an existing socksdroid tunnel.

Exploratory probe for the Copilot-via-Edge platform: clears Edge, walks the
first-run experience, and returns Copilot's answer text for one prompt. Nodes are
matched by text/content-desc because the Copilot surface is a WebView with no
resource-ids. Assumes the tunnel is already up — it never touches gost/socksdroid.
"""
import re, subprocess, sys, time

PKG = "com.microsoft.emmx"

def sh(serial, cmd, timeout=30):
    return subprocess.run(f'adb -s "{serial}" {cmd}', shell=True,
                          capture_output=True, text=True, timeout=timeout)

def dump(serial):
    sh(serial, "shell uiautomator dump /sdcard/ui.xml", 30)
    xml = sh(serial, "exec-out cat /sdcard/ui.xml", 30).stdout
    nodes = []
    for s in re.findall(r'<node[^>]*?/?>', xml):
        def attr(k):
            m = re.search(rf'{k}="([^"]*)"', s)
            return m.group(1) if m else ""
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        nodes.append({"text": attr("text"), "desc": attr("content-desc"),
                      "id": attr("resource-id"), "cls": attr("class"),
                      "xy": ((x1 + x2) // 2, (y1 + y2) // 2)})
    return nodes

def find(nodes, text=None, desc=None, id_=None, cls=None):
    for n in nodes:
        if text is not None and n["text"] != text: continue
        if desc is not None and desc not in n["desc"]: continue
        if id_ is not None and not n["id"].endswith(id_): continue
        if cls is not None and not n["cls"].endswith(cls): continue
        return n
    return None

def tap(serial, node, settle=3):
    x, y = node["xy"]
    sh(serial, f"shell input tap {x} {y}", 15)
    time.sleep(settle)

def top_activity(serial):
    out = sh(serial, "shell dumpsys activity activities", 30).stdout
    m = re.search(r'topResumedActivity=\S+ \S+ (\S+)', out)
    return m.group(1) if m else "?"

def dismiss_fre(serial, rounds=8):
    """Walk the first-run screens. Each is identified by a unique node; the loop
    exits once the new tab page (the Copilot entry point) is reachable."""
    for _ in range(rounds):
        nodes = dump(serial)
        if find(nodes, id_="edge_location_bar_copilot_button"):
            return True
        for kw in (dict(text="Not now"), dict(id_="fre_sign_in_later"),
                   dict(text="Confirm"), dict(id_="permission_deny_button"),
                   dict(text="Don't allow")):
            n = find(nodes, **kw)
            if n:
                print(f"  fre: tap {kw}", flush=True)
                tap(serial, n, 4)
                break
        else:
            print(f"  fre: nothing to tap on {top_activity(serial)}", flush=True)
            time.sleep(3)
    return bool(find(dump(serial), id_="edge_location_bar_copilot_button"))

def open_url(serial, url):
    sh(serial, f'shell am start -a android.intent.action.VIEW -d "{url}" -n {PKG}/com.microsoft.ruby.Main', 30)
    time.sleep(8)
    return " ".join(n["text"] for n in dump(serial) if n["text"])

def ask_copilot(serial, prompt, wait_s=60):
    nodes = dump(serial)
    btn = find(nodes, id_="edge_location_bar_copilot_button")
    if not btn:
        return None, "no copilot button"
    tap(serial, btn, 7)

    box = find(dump(serial), cls="EditText")
    if not box:
        return None, "no composer"
    tap(serial, box, 3)
    sh(serial, f"shell input text '{prompt.replace(' ', '%s')}'", 30)
    time.sleep(2)

    # Gate the submit on the composer actually holding text: the right-edge button
    # is "Start a voice Call" until then, and tapping it opens a voice call.
    box = find(dump(serial), cls="EditText")
    if not box or not box["text"].strip():
        return None, "composer empty after typing"
    nodes = dump(serial)
    send = find(nodes, desc="Send")
    if not send:
        return None, "no send button (composer text not registered)"
    tap(serial, send, 5)

    deadline = time.time() + wait_s
    answer = []
    while time.time() < deadline:
        nodes = dump(serial)
        seen = False
        out = []
        for n in nodes:
            if n["desc"].startswith("Sent by you."):
                seen = True
                continue
            if seen and n["text"] and n["cls"].endswith("TextView"):
                out.append(n["text"])
        if any(len(t) > 40 for t in out):
            answer = out
            break
        time.sleep(5)
    return answer, None

if __name__ == "__main__":
    serial, prompt = sys.argv[1], sys.argv[2]
    sh(serial, f"shell pm clear {PKG}", 60)
    sh(serial, f"shell am force-stop {PKG}", 30)
    sh(serial, f"shell monkey -p {PKG} -c android.intent.category.LAUNCHER 1", 30)
    time.sleep(7)
    print("fre ok:", dismiss_fre(serial), "activity:", top_activity(serial), flush=True)
    ans, err = ask_copilot(serial, prompt)
    print("ERR:", err) if err else [print(" |", t) for t in ans]
