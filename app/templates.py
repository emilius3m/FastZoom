from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone
import math

# Create a Jinja2 environment with auto-reload enabled
jinja_env = Environment(loader=FileSystemLoader("app/templates"), auto_reload=True)

# Custom date formatting function to replace jinja2-moment
class CustomMoment:
    def __init__(self, date):
        if isinstance(date, str):
            # Try to parse string dates
            try:
                self.date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                self.date = datetime.now(timezone.utc)
        elif hasattr(date, 'replace'):  # datetime object
            self.date = date
        else:
            self.date = datetime.now(timezone.utc)

    def fromNow(self):
        """Return relative time string (e.g., '2 hours ago', '3 days ago')"""
        now = datetime.now(timezone.utc)
        diff = now - self.date.replace(tzinfo=timezone.utc)

        # Calculate time differences
        seconds = diff.total_seconds()
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24
        months = days / 30
        years = days / 365

        # Format relative time
        if abs(seconds) < 60:
            return "just now"
        elif abs(minutes) < 60:
            unit = "minute" if abs(minutes) < 2 else "minutes"
            return f"{int(abs(minutes))} {unit} ago"
        elif abs(hours) < 24:
            unit = "hour" if abs(hours) < 2 else "hours"
            return f"{int(abs(hours))} {unit} ago"
        elif abs(days) < 30:
            unit = "day" if abs(days) < 2 else "days"
            return f"{int(abs(days))} {unit} ago"
        elif abs(months) < 12:
            unit = "month" if abs(months) < 2 else "months"
            return f"{int(abs(months))} {unit} ago"
        else:
            unit = "year" if abs(years) < 2 else "years"
            return f"{int(abs(years))} {unit} ago"

    def format(self, fmt):
        """Format date according to given format string"""
        return self.date.strftime(fmt)

    def __str__(self):
        return self.date.isoformat()

def moment(date):
    """Factory function to create CustomMoment instances"""
    return CustomMoment(date)

# Add custom moment function to Jinja2 globals
jinja_env.globals['moment'] = moment

# Use the custom environment in Jinja2Templates
templates = Jinja2Templates(env=jinja_env)
