import sys

import startup_utils

def main():
    report = startup_utils.disable_startup()
    if report["registry_ok"] and report["task_ok"]:
        removed = ", ".join(report["removed_tasks"]) if report["removed_tasks"] else "none"
        print(f"Startup disabled. Removed tasks: {removed}")
        return

    errors = []
    if report["registry_error"]:
        errors.append(report["registry_error"])
    errors.extend(report["task_errors"])
    print("Failed to fully remove startup.")
    if errors:
        print("\n".join(errors))
    sys.exit(1)

if __name__ == "__main__":
    main()
