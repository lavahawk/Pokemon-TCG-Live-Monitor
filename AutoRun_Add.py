import os
import sys

import startup_utils

def main():
    report = startup_utils.enable_startup(os.path.dirname(os.path.abspath(__file__)))
    methods = []
    if report["registry_ok"]:
        methods.append("Registry Run key")
    if report["task_ok"]:
        methods.append("Scheduled Task (elevated)")

    if methods:
        print("Startup enabled in headless mode.")
        print("Methods registered: " + ", ".join(methods))
        return

    errors = [msg for msg in (report["registry_error"], report["task_error"]) if msg]
    print("Failed to enable startup.")
    if errors:
        print("\n".join(errors))
    sys.exit(1)

if __name__ == "__main__":
    main()
