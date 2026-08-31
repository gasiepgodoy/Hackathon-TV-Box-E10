import subprocess
import time
import os
import re

# Discover Xorg parameters dynamically from active processes
display = ":0"
xauth = ""

try:
    ps_output = subprocess.check_output(["ps", "-ef"], text=True)
    for line in ps_output.split("\n"):
        if "Xorg" in line and "-auth" in line:
            disp_match = re.search(r"\s(:\d+)\s", line)
            if disp_match:
                display = disp_match.group(1)
            auth_match = re.search(r"-auth\s+([^\s]+)", line)
            if auth_match:
                xauth = auth_match.group(1)
            print(f"Discovered active Xorg: display={display}, auth={xauth}")
            break
except Exception as e:
    print(f"Xorg auto-discovery failed: {e}")

env = os.environ.copy()
env["DISPLAY"] = display
if xauth:
    env["XAUTHORITY"] = xauth

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print(f"Starting main_gui.py on display {display} with system_optimizer...")
proc = subprocess.Popen(
    ["python3", "main_gui.py"],
    cwd=project_root,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(6)

poll = proc.poll()
if poll is None:
    print("SUCCESS: main_gui.py is running on display!")
    try:
        import select
        r, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.5)
        for pipe in r:
            print(f"--- Output from {pipe.name} ---")
            print(pipe.read(4096))
    except Exception as e:
        print(f"Error reading pipe output: {e}")
    proc.terminate()
else:
    print(f"FAILED: main_gui.py exited with code {poll}")
    stdout, stderr = proc.communicate()
    print("=== STDOUT ===")
    print(stdout)
    print("=== STDERR ===")
    print(stderr)
