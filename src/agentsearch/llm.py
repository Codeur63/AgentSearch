from groq import Groq
from agentsearch.settings import settings
from temporalio import activity
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# @activity.defn(name='ask_llm')
def ask_llm(question:str) -> str:
    
    logger.info("Envoi de la question au LLM")
    try :
        reponse = client.chat.completions.create(
            model=settings["MODEL"],
            messages = [
                {
                    'role':'system',
                    'content': """ Tu es agent de recherche intelligent. Tu reponds au question en te basant uniquement sur les resultats de recherche fournis. Si les resultats ne permettent pas que tu reponde indique clairement que tu ne dispose pas assez d'information suffisante. Ne presente pas une information absente des resultats comme un fait."""
                },
                {
                    'role':'user',
                    'content': question
                }        
            ],
                temperature=0.2
        )

        reponse = reponse.choices[0].message.content.strip()

        return reponse 

    except Exception as e:
        logger.error(f"Echec de la reponse du LLM")

if __name__ == "__main__":
    question = input("Human : ")
    reponse = ask_llm(question)
    print(f"reponse : {reponse}")