import os


class BotSettings:
    def __init__(self):
        self.BOT_TOKEN = os.environ["BOT_TOKEN"]
        self.DATABASE_URL = (
            f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASS']}"
            f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}"
            f"/{os.environ['DB_NAME']}?sslmode=disable"
        )
        self.SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "30"))
        self.MAX_DAYS_AHEAD = int(os.environ.get("MAX_DAYS_AHEAD", "14"))
        self.MAX_BOOKING_SLOTS = int(os.environ.get("MAX_BOOKING_SLOTS", "6"))


settings = BotSettings()
