# AgentSearch

Assistant de recherche documentaire et de création de publications avec validation humaine, orchestré par Temporal. (Human-in-the-loop)

**Statut : prototype fonctionnel à tester avec vos services externes.** Le parcours de recherche, vérification, validation, rédaction et autorisation de publication est implémenté. Les tests utilisent des sources, modèles et plateformes simulés ; aucun post réel n’a été envoyé pendant le développement.

## Objectif et fonctionnement

À partir d’une question comme « Quelles sont les actualités de l’IA aujourd’hui ? », AgentSearch :

1. Recherche des sources sur le Web et sélectionne les résultats pertinents.
2. Télécharge les pages, extrait les textes et les métadonnées de publication.
3. Contrôle leur pertinence, leur volume, leur diversité et leur fraîcheur si nécessaire.
4. Produit une synthèse sourcée, puis vérifie ses affirmations avec des extraits exacts des documents.
5. Relance la recherche si les informations ou les preuves sont insuffisantes, dans les limites configurées.
6. Soumet la synthèse à l’utilisateur, qui peut la valider ou demander de nouvelles recherches.
7. Demande le ton, la plateforme et la destination, puis rédige et vérifie un brouillon.
8. Soumet ce brouillon à validation. Une correction éditoriale relance la rédaction ; une correction des données relance la recherche.
9. Attend une autorisation distincte avant de transmettre la version approuvée au connecteur de publication.
10. Temporal pour voir toutes les activites, les echecs et coordoner toutes les etapes


## Architecture

Le projet veut implementer une architecture modulaire. Temporal orchestre le travail; les services applicatifs appliquent les règles; les adaptateurs (mcp) accèdent aux fournisseurs externes.

| Module | Responsabilité |
| --- | --- |
| `domain/` | Contrats Pydantic, décisions, versions et statuts ; aucune dépendance à Temporal |
| `application/` | Préparation des recherches, synthèse, vérification, rédaction et publication unique |
| `ports/` | Interfaces de modèle, recherche, collecte, publication et stockage |
| `infrastructure/` | Adaptateur Groq, client MCP, registre SQLite |
| `orchestration/` | Workflow Temporal, activités et assemblage des workers |
| `interfaces/` | Interface terminal et décisions humaines |
| `tools/` | Adaptateurs existants de recherche, filtrage, collecte et contrôle documentaire |
| `agent/` | Activités de vérification et de rédaction |
| `publishing/` | Connecteur LinkedIn |

Les anciens chemins `schema/schema.py` et `worklows/workflow.py` restent disponibles comme imports de compatibilité. Le nouveau workflow reçoit un `ResearchRequest` : les historiques de l’ancien prototype ne constituent pas une migration compatible ; démarrer de nouvelles tâches avec cette version.

```text
Question → Recherche → Extraction → Contrôle → Synthèse → Vérification
              ↑                                             │
              └──────────── Compléments nécessaires ────────┘
                                                            ↓
                                               Validation de la synthèse
                                                            ↓
                                               Ton, format et destination
                                                            ↓
                                                Rédaction et vérification
                                                            ↓
                                               Validation du brouillon
                                                            ↓
                                               Autorisation de publication
                                                            ↓
                                                 LinkedIn ou outil MCP
```

## Installation

Prérequis : Python 3.12+, `uv`, un serveur Temporal local et une clé Groq. Docker et Docker Compose permettent de lancer l’infrastructure fournie.

```bash
uv sync
cp .env.example .env
```

Renseigner au minimum `GROQ_API_KEY` et `GROQ_MODEL`, avec un modèle accessible sur votre compte GROQ. Le modèle doit accepter les réponses JSON utilisées par le vérificateur.

Démarrer Temporal :

```bash
docker compose up -d
```

Le fichier Compose expose le service sur `localhost:7233` et l’interface Temporal sur `http://localhost:8080`. Cette configuration est destinée au développement local.

## Utilisation

Run le fichier main ```bash uv run main.py```

## Publication et MCP

### LinkedIn

Le connecteur utilise la [Posts API officielle](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api). L’obtention du jeton et des accès LinkedIn se fait en dehors de cette application. La destination du brouillon doit correspondre à l’auteur configuré ; un changement de compte après approbation bloque la diffusion.

L’interface demande de saisir `PUBLIER` après validation du brouillon. Sans cette autorisation, aucun appel de publication n’est émis.

### Autres plateformes via MCP

Facebook et les autres applications peuvent être branchés avec un serveur MCP fournissant un outil de publication compatible. **Le dépôt ne contient pas de connecteur Facebook natif.** Le client accepte HTTPS ou HTTP sur une adresse locale. L’authentification MCP spécifique à un fournisseur reste à ajouter ; utiliser actuellement un serveur local ou un accès sécurisé adapté à votre infrastructure.

L’outil configuré reçoit :

```json
{
  "publication_id": "identifiant-de-tache:draft:1",
  "platform": "facebook",
  "destination": "identifiant-de-page",
  "content": "Texte approuvé"
}
```

Il doit retourner, en contenu structuré ou texte JSON :

```json
{
  "platform": "facebook",
  "remote_id": "identifiant-distant",
  "status": "published",
  "url": "https://plateforme.example/publication"
}
```

Le serveur `mcp_server/server.py` fourni est uniquement une ébauche d’aperçu ; il ne publie pas et ne satisfait pas encore ce contrat de diffusion.


## Tests
Tests déterministes, sans clé API ni réseau externe :

```bash
uv run pytest -q
```

## Limites actuelles

- Le vérificateur juge la fidélité aux sources et contrôle les extraits exacts ; il ne garantit pas la vérité des sources ni l’exhaustivité de son analyse.
- Les dates dépendent des métadonnées extraites. Une date d’article ne garantit pas que tous les événements décrits ont eu lieu ce jour-là.
- La pertinence documentaire reste lexicale ; la sélection ne constitue pas un classement de fiabilité éditoriale.
- Les pages nécessitant JavaScript, connexion ou paiement peuvent ne pas être exploitables. Les textes sont limités à 30 000 caractères par document.
- La collecte interdit les IP directes et les résolutions privées ; elle fige l’IP publique utilisée pour la connexion et contrôle chaque redirection.
- L’interface et le serveur Temporal local supposent un opérateur de confiance ; authentification multiutilisateur, contrôle des rôles et déploiement public restent à concevoir.
- Les tests ne remplacent pas une validation avec les comptes Groq, LinkedIn et les serveurs MCP réellement utilisés.

Le contexte, les décisions et les validations sont conservés dans [README_GPT.md](README_GPT.md).

## limite 
Pas cle API payante pour supporte les tokens.   
prévoir une sauvegarde et un stockage durable avant tout déploiement ou recréation de la base.
