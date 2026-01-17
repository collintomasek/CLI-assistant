import os
import re
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

# 1. LOAD ENVIRONMENT VARIABLES
# This looks for the ".env" file in your project folder
load_dotenv()

# 2. INITIALIZE CLIENT
# os.getenv grabs the key we saved in your .env file
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ Error: OPENAI_API_KEY not found. Check your .env file.")
    exit()

client = OpenAI(api_key=api_key)

# 3. CONVERSATION HISTORY (MEMORY)
conversation_history = []

def is_command_safe(command):
    """
    Safety filter that checks if a command is dangerous.
    Returns (is_safe: bool, reason: str)
    """
    # Convert to lowercase for case-insensitive matching
    cmd_lower = command.lower().strip()
    
    # Dangerous patterns to block
    dangerous_patterns = [
        # Linux/Mac destructive commands
        (r'rm\s+(-[rf]+\s+)?/', "Attempts to delete system directories"),
        (r'rm\s+-rf\s+\*', "Attempts to recursively delete all files"),
        (r'dd\s+.*of=/dev/(sd|hd)', "Attempts to overwrite disk"),
        (r'mkfs\.\w+\s+/dev/', "Attempts to format a disk"),
        (r':\(\)\{\s*:\|:&\s*\};:', "Fork bomb that crashes the system"),
        (r'chmod\s+-R\s+777\s+/', "Makes all system files world-writable"),
        (r'mv\s+/\s+', "Attempts to move root directory"),
        
        # Windows destructive commands
        (r'del\s+/[fqs]+\s+c:\\', "Attempts to delete Windows system files"),
        (r'format\s+c:', "Attempts to format system drive"),
        (r'rd\s+/s\s+/q\s+c:\\', "Attempts to remove Windows system directories"),
        (r'rmdir\s+/s\s+/q\s+c:\\', "Attempts to remove Windows system directories"),
        (r'del\s+.*\*\.\*', "Attempts to delete all files"),
        
        # System modification
        (r'sudo\s+rm\s+-rf', "Elevated deletion command"),
        (r'chown\s+-R\s+.*\s+/', "Changes ownership of system files"),
        
        # Network attacks
        (r':(){ :|:& };:', "Fork bomb"),
        (r'wget\s+.*\|\s*sh', "Downloads and executes unknown scripts"),
        (r'curl\s+.*\|\s*bash', "Downloads and executes unknown scripts"),
    ]
    
    # Check each dangerous pattern
    for pattern, reason in dangerous_patterns:
        if re.search(pattern, cmd_lower):
            return False, f"🚨 BLOCKED: {reason}"
    
    # Additional checks for specific keywords
    dangerous_keywords = {
        '/dev/sda': "Accesses system disk directly",
        '/dev/null >': "Redirects critical output",
        '> /dev/sda': "Writes to system disk",
    }
    
    for keyword, reason in dangerous_keywords.items():
        if keyword in cmd_lower:
            return False, f"🚨 BLOCKED: {reason}"
    
    return True, "Safe"

def run_terminal_command(command):
    """Executes a terminal command and returns the output/error."""
    try:
        # shell=True allows for pipes and redirects (e.g., "mkdir test && cd test")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            return result.stdout if result.stdout else "✅ Success (no output)."
        else:
            return f"⚠️ Command Error: {result.stderr}"
    except Exception as e:
        return f"❌ System Error: {str(e)}"

def jarvis_agent():
    print("--- Jarvis-Lite CLI Agent Active ---")
    print("✅ Safety Filter: ON")
    print("✅ Memory: ON")
    print("(Type 'exit' or 'quit' to stop)\n")

    while True:
        user_input = input("What can I do for you? > ")

        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break

        # 4. ASK THE AI FOR THE COMMAND (with memory context)
        system_prompt = (
            "You are a CLI Assistant for Windows/Mac. "
            "Convert the user's request into a single valid terminal command. "
            "Output ONLY the raw command. No markdown, no explanation, no backticks. "
            "You can reference previous commands from the conversation history if needed."
        )

        try:
            # Build messages with conversation history (memory)
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history for context
            for entry in conversation_history[-10:]:  # Keep last 10 interactions
                messages.append({"role": "user", "content": entry["user_input"]})
                messages.append({"role": "assistant", "content": entry["command"]})
                if entry.get("result"):
                    messages.append({"role": "system", "content": f"Previous result: {entry['result'][:200]}"})
            
            # Add current request
            messages.append({"role": "user", "content": user_input})
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )

            command = response.choices[0].message.content.strip()
            
            # Remove any accidentally generated backticks (common AI mistake)
            command = command.replace("`", "")

            # 5. SAFETY FILTER CHECK
            is_safe, safety_reason = is_command_safe(command)
            
            if not is_safe:
                print(f"\n{safety_reason}")
                print(f"Command blocked: {command}\n")
                # Store blocked command in history
                conversation_history.append({
                    "user_input": user_input,
                    "command": command,
                    "result": "BLOCKED: " + safety_reason
                })
                continue

            # 6. USER CONFIRMATION
            print(f"\n🤖 Agent wants to run: {command}")
            confirm = input("Confirm execution? (y/n): ")

            if confirm.lower() == 'y':
                print("Running...")
                output = run_terminal_command(command)
                print(f"RESULT:\n{output}\n")
                
                # Store in memory
                conversation_history.append({
                    "user_input": user_input,
                    "command": command,
                    "result": output
                })
            else:
                print("Skipped.\n")
                # Store skipped command in history
                conversation_history.append({
                    "user_input": user_input,
                    "command": command,
                    "result": "User skipped execution"
                })

        except Exception as e:
            print(f"API Error: {e}")

if __name__ == "__main__":
    jarvis_agent()