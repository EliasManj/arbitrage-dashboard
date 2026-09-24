import os
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit

load_dotenv()

if __name__ == "__main__":
    playdoit = Playdoit()
    events = Playdoit().get_events()

    for event in events:
        print(event)