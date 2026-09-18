import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

logger.info("Recuperation des variables d'environnement")

settings = {
    "API" : os.getenv("GROQ_API_KEY"),
    "MODEL": os.getenv("GROQ_MODEL")
}