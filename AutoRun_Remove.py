import subprocess

def remove_task(task_name="StartTCGLiveMonitor"):
    # Define the command to delete the task using schtasks
    command = f'schtasks /delete /tn "{task_name}" /f'
    
    # Run the command using subprocess
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Task '{task_name}' removed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to remove task '{task_name}'. Error: {e.stderr.decode().strip()}")

def main():
    # Remove the scheduled task
    remove_task()

if __name__ == "__main__":
    main()
