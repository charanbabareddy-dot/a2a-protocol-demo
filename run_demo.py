"""
Run both agents in one command: starts the Delivery Agent in the background,
then the Shop Assistant talks to it over A2A.

    python run_demo.py
"""

import threading

import delivery_agent
import shop_assistant

if __name__ == "__main__":
    server = delivery_agent.make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        shop_assistant.main()
    finally:
        server.shutdown()
