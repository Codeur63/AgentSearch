"""Tools pour faire la recherche sur le net """
import asyncio
from datetime import timedelta
from ddgs import DDGS
from temporalio.client import Client
from temporalio.worker import Worker  
from temporalio import activity, workflow

@activity.defn(name='search_web')
async def search_web(question:str) -> str:
    print(f"[Activity] Recherche en cours")

    try:
        with DDGS() as ddgs:
            print("Search ... ")
            resultats = list(ddgs.text(question, max_results=5))

        print(f"[Acitviy] resultats : {len(resultats)}")
        if not resultats:
            return "[Activiy] Pas de resultats trouve sur le web"

        rendu = []
        for i, res in enumerate(resultats, 1):
            rendu.append(f"source {i}: {res['title']}\nExtrait: {res['body']}\n URL:{res['href']}")

        return "\n".join(rendu)

    except Exception as e:
        raise RuntimeError(f"Echec de la recherche web: {str(e)}")    
