import sys
import threading
import os
import time
import httpx
import gradio as gr

# Silence internal Gradio event loop garbage collection notices on Linux
def _custom_unraisablehook(unraisable):
    if unraisable.exc_type is ValueError and "Invalid file descriptor" in str(unraisable.exc_value):
        return
    sys.__unraisablehook__(unraisable)

sys.unraisablehook = _custom_unraisablehook

# Hugging Face ZeroGPU Startup Validator
try:
    import spaces
    @spaces.GPU
    def zero_gpu_keepalive(x: int = 1):
        return f"ZeroGPU Engaged: {x}"
except Exception as e:
    print(f"ZeroGPU notice: {e}")

import socket

_SINGLE_INSTANCE_SOCKET = None

def acquire_single_instance_lock(port: int = 18999) -> bool:
    global _SINGLE_INSTANCE_SOCKET
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.listen(1)
        _SINGLE_INSTANCE_SOCKET = s
        print(f"Single-instance lock successfully acquired on port {port}.")
        return True
    except Exception as e:
        print(f"Single-instance lock check for port {port}: {e}. Skipping duplicate bot thread.")
        return False

# Start Nym Bot in a background thread after Gradio initializes
def run_nym_bot():
    if not acquire_single_instance_lock(18999):
        print("Duplicate Nym Bot startup prevented cleanly.")
        return

    time.sleep(3)  # Short delay to allow Gradio to bind port 7860 first
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        import main
        main.main()
    except Exception as e:
        print(f"Nym Bot Execution Error: {e}")
    finally:
        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            pass

bot_thread = threading.Thread(target=run_nym_bot, daemon=True)
bot_thread.start()

# Background Self-Ping / Keep-Alive Monitor
SPACE_HOST = os.getenv("SPACE_HOST", "")

def self_ping_loop():
    if not SPACE_HOST:
        print("Self-ping notice: SPACE_HOST env var not present (running locally or direct).")
        return
    url = f"https://{SPACE_HOST}"
    print(f"Self-ping initialized targeting: {url}")
    time.sleep(45)
    while True:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(url)
                print(f"Self-ping heartbeat sent to {url} - Status {r.status_code}")
        except Exception as e:
            print(f"Self-ping heartbeat notice: {e}")
        time.sleep(240)

ping_thread = threading.Thread(target=self_ping_loop, daemon=True)
ping_thread.start()

# Sleek Gradio Interface for Hugging Face Space Heartbeat
with gr.Blocks(title="Nym Bot Protocol") as demo:
    gr.Markdown("# 🌙 Nym Bot Protocol")
    gr.Markdown("### Status: **Operational ✧**")
    gr.Markdown("Nym Discord Bot is active and running 24/7 on Hugging Face Spaces.")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, ssr_mode=False)
