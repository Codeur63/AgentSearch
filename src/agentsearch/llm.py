import re
import json
from groq import Groq
from agentsearch.settings import settings
from temporalio import activity


client = Groq(api_key=settings["API"])

@activity.defn(name='ask_llm')
async def ask_llm(question:str, research_result:str) -> str:
    reponse = client.chat.completions.create(
        model=settings["MODEL"],
        messages = [
            {
               'role':'system',
               'content': """ Tu es agent de recherche intelligent. Tu reponds au question en te basant uniquement sur les resultats de recherche fournis. Si les resultats ne permettent pas que tu reponde indique clairement que tu ne dispose pas assez d'information suffisante. Ne presente pas une information absente des resultats comme un fait."""
            },
            {
            'role':'user',
            'content': f"""
            Question: {question}
            Resultats de recherche: {research_result}
            
            """
            }        
        ],
        temperature=0.2
    )


    reponse = reponse.choices[0].message.content.strip()

    return reponse