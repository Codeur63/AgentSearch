"""Publication protégée contre une réémission après résultat incertain."""

from agentsearch.domain.models import PublicationCommand, PublicationReceipt
from agentsearch.ports.services import PublicationStore, Publisher


def publish_once(command: PublicationCommand, publisher: Publisher, ledger: PublicationStore) -> PublicationReceipt:
    # Revalide également les objets construits en mémoire avant le moindre effet externe.
    command = PublicationCommand.model_validate(command.model_dump())
    previous = ledger.reserve(command)
    if previous:
        return previous
    try:
        receipt = publisher.publish(command.draft)
    except Exception:
        # Le serveur peut avoir publié avant une coupure réseau : aucune répétition automatique.
        receipt = PublicationReceipt(platform=command.draft.platform, remote_id='', status='unknown',
                                     detail='Réponse de publication incertaine ; vérifier la plateforme avant de republier')
    ledger.record(command, receipt)
    return receipt
