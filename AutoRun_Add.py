import os
import subprocess
import sys

def create_task(script_path, task_name="StartTCGLiveMonitor", python_exe="python.exe"):
    # Define the command to create the task using schtasks
    command = f'schtasks /create /tn "{task_name}" /tr "{python_exe} {script_path}" /sc onlogon /rl highest /f'

    # Run the command using subprocess
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Task '{task_name}' created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to create task '{task_name}'. Error: {e.stderr.decode().strip()}")

def main():
    # Get the path to the Python script to be run
    script_path = os.path.abspath("TCGLiveMonitor.py")
    
    # Optionally, allow the user to specify a custom Python executable
    python_exe = sys.executable  # Default to the current Python executable

    # Create the scheduled task
    create_task(script_path, python_exe=python_exe)

if __name__ == "__main__":
    main()
