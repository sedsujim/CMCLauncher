# core/installer.py
import os
import time
import traceback
import minecraft_launcher_lib

LOGS_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

def _log_for(version):
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(LOGS_DIR, f"install-{version}-{ts}.log")
    return path

def ensure_version_installed(version: str, minecraft_dir: str, callback_map=None):
    """
    Ensure 'version' is installed in minecraft_dir.
    - callback_map: optional mapping containing 'setStatus', 'setProgress' callables.
    Returns True on success, raises Exception on failure and writes log.
    """
    # quick check
    version_folder = os.path.join(minecraft_dir, "versions", version)
    version_json = os.path.join(version_folder, f"{version}.json")
    if os.path.exists(version_json):
        return True

    log_path = _log_for(version)
    try:
        # if caller didn't provide callback_map, create safe map
        if callback_map is None:
            def setStatus(t): pass
            def setProgress(p): pass
            callback_map = {"setStatus": setStatus, "setProgress": setProgress}

        # call library install (this will download and extract)
        minecraft_launcher_lib.install.install_minecraft_version(
            version,
            minecraft_dir,
            callback=callback_map
        )

        # verify result
        if os.path.exists(version_json):
            return True
        else:
            raise RuntimeError(f"install reported success but {version_json} missing")
    except Exception as ex:
        # write detailed log for debugging
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("Exception during ensure_version_installed\n")
            f.write(f"version: {version}\n")
            f.write(f"minecraft_dir: {minecraft_dir}\n")
            f.write("Exception:\n")
            traceback.print_exc(file=f)
        # re-raise so caller can handle / show message
        raise

