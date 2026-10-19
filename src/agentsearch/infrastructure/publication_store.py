"""Registre SQLite des publications ; conserver ce fichier entre les reprises."""

import hashlib
import sqlite3
from pathlib import Path

from agentsearch.domain.models import PublicationCommand, PublicationReceipt


class PublicationLedger:
    """Registre durable partagé par les workers exécutés sur la même machine."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS publications '
                       '(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, receipt TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def reserve(self, command: PublicationCommand) -> PublicationReceipt | None:
        digest = hashlib.sha256(command.model_dump_json().encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT fingerprint, receipt FROM publications WHERE id=?',
                             (command.publication_id,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError('Identifiant déjà utilisé pour un autre contenu')
                if row[1]:
                    return PublicationReceipt.model_validate_json(row[1])
                return PublicationReceipt(platform=command.draft.platform, remote_id='', status='unknown',
                                          detail='Publication déjà engagée : vérifier la plateforme avant toute nouvelle tentative')
            db.execute('INSERT INTO publications (id, fingerprint) VALUES (?, ?)',
                       (command.publication_id, digest))
        return None

    def record(self, command: PublicationCommand, receipt: PublicationReceipt) -> None:
        with self.connect() as db:
            db.execute('UPDATE publications SET receipt=? WHERE id=?',
                       (receipt.model_dump_json(), command.publication_id))

