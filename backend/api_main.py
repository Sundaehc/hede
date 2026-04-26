from api.app import create_app
from config import load_settings

settings = load_settings(require_database=True)
app = create_app(settings=settings)
