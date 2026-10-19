"""Connecteur LinkedIn Posts API ; aucune publication au chargement du module."""

import re

import httpx

from agentsearch.domain.models import PublicationDraft, PublicationReceipt


class LinkedInPublisher:
    def __init__(self, token: str, author: str, api_version: str,
                 client: httpx.Client | None = None) -> None:
        if not token or not re.fullmatch(r'urn:li:(person|organization):[A-Za-z0-9_-]+', author):
            raise ValueError('Configurer le jeton LinkedIn et un auteur URN valide')
        if not re.fullmatch(r'20\d{2}(0[1-9]|1[0-2])', api_version):
            raise ValueError('Configurer LINKEDIN_API_VERSION au format YYYYMM')
        self.token, self.author, self.api_version = token, author, api_version
        self.client = client

    def validate(self, draft: PublicationDraft) -> None:
        if draft.platform != 'linkedin' or draft.destination != self.author:
            raise ValueError('Le compte LinkedIn doit correspondre à la destination approuvée')
        if len(draft.content) > 3000:
            raise ValueError('Publication LinkedIn trop longue')

    def publish(self, draft: PublicationDraft) -> PublicationReceipt:
        self.validate(draft)
        if self.client is None:
            with httpx.Client(timeout=30, trust_env=False) as client:
                return self._send(draft, client)
        return self._send(draft, self.client)

    def _send(self, draft: PublicationDraft, client: httpx.Client) -> PublicationReceipt:
        response = client.post('https://api.linkedin.com/rest/posts', headers={
            'Authorization': f'Bearer {self.token}', 'LinkedIn-Version': self.api_version,
            'X-Restli-Protocol-Version': '2.0.0',
        }, json={
            'author': self.author, 'commentary': draft.content, 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [],
                             'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False,
        })
        remote_id = response.headers.get('x-restli-id', '')
        if response.status_code == 201 and remote_id:
            return PublicationReceipt(platform='linkedin', remote_id=remote_id,
                                      url=f'https://www.linkedin.com/feed/update/{remote_id}/', status='published')
        status = 'failed' if 400 <= response.status_code < 500 else 'unknown'
        return PublicationReceipt(platform='linkedin', remote_id='', status=status,
                                  detail=f'Réponse LinkedIn HTTP {response.status_code} ; vérifier le compte et les droits')
