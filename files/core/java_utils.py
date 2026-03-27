# core/java_utils.py
import shutil
import subprocess

COMMON_JAVA_CANDIDATES = [
    "java",  # PATH
]

# On Windows we can also check common Program Files paths (optional)
WINDOWS_CANDIDATES = [
    r"C:\Program Files\Java\jre1.8.0\bin\java",
    r"C:\Program Files\Java\jre1.8.0_241\bin\java",
    r"C:\Program Files\Java\jdk1.8.0\bin\java",
    r"C:\Program Files\Java\jre-8u211-windows-x64\bin\java"
]

LINUX_CANDIDATES = [
    "/usr/bin/java",
    "/usr/lib/jvm/java-8-openjdk-amd64/bin/java",
    "/usr/lib/jvm/java-11-openjdk-amd64/bin/java"
]

def find_java_candidates():
    candidates = set()
    # PATH java
    p = shutil.which("java")
    if p:
        candidates.add(p)
    # extra OS specific candidates
    try:
        import platform
        sysplat = platform.system().lower()
        if "windows" in sysplat:
            candidates.update([c for c in WINDOWS_CANDIDATES if shutil.which(c) or os.path.exists(c)])
        else:
            candidates.update([c for c in LINUX_CANDIDATES if os.path.exists(c)])
    except Exception:
        pass
    return list(candidates)

def java_version_string(java_exec):
    try:
        proc = subprocess.run([java_exec, "-version"], capture_output=True, text=True)
        out = proc.stderr.strip() + "\n" + proc.stdout.strip()
        return out
    except Exception:
        return ""

def is_java8(java_exec):
    s = java_version_string(java_exec)
    return "1.8" in s or "Java(TM) SE Runtime Environment (build 1.8" in s
