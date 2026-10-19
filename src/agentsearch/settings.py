"""Configuration locale ; aucune valeur sensible n'est journalisée."""
import os

from dotenv import load_dotenv

load_dotenv()
settings = {'API': os.getenv('GROQ_API_KEY'), 'MODEL': os.getenv('GROQ_MODEL')}
