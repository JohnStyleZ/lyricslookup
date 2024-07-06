import sys

# Add your project directory to the sys.path
project_home = u'/home/johnstylez/mysite'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Import your Flask application
from app import app as application  # Import the app module and use 'app' as the WSGI application
