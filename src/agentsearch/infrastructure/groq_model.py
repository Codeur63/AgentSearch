"""Adaptateur Groq partagé par la synthèse, la vérification et la rédaction."""

from groq import Groq

from agentsearch.settings import settings


class GroqLanguageModel:
    def complete(self, system: str, user: str, *, json_output: bool = False) -> str:
        if not settings['API'] or not settings['MODEL']:
            raise ValueError('Configurer GROQ_API_KEY et GROQ_MODEL')
        with Groq(api_key=settings['API'], timeout=60, max_retries=0) as client:
            kwargs = {'response_format': {'type': 'json_object'}} if json_output else {}
            response = client.chat.completions.create(
                model=settings['MODEL'],
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                temperature=0.2, max_completion_tokens=4096, **kwargs,
            )
        text = response.choices[0].message.content
        if not text or not text.strip():
            raise ValueError('Réponse vide du modèle')
        return text.strip()
