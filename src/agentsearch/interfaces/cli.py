"""Interface terminal : démarrer, reprendre et valider une tâche persistante."""

import argparse
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from agentsearch.application.research import make_request
from agentsearch.domain.models import EditorialPreferences, HumanDecision, WorkflowSnapshot, WorkflowStatus
from agentsearch.orchestration.workers import running_workers
from agentsearch.orchestration.workflows import ContentWorkflow, MAIN_TASK_QUEUE

TERMINAL_STATES = {
    WorkflowStatus.COMPLETED, WorkflowStatus.NEEDS_INPUT, WorkflowStatus.FAILED, WorkflowStatus.EXPIRED,
}


async def prompt(text: str) -> str:
    return (await asyncio.to_thread(input, text)).strip()


async def revision_feedback() -> str:
    while True:
        feedback = await prompt('Corrections demandées : ')
        if feedback:
            return feedback
        print('Indiquer au moins une correction pour poursuivre.')


async def preferences() -> EditorialPreferences:
    tone = await prompt('Ton [informatif / pédagogique / personnalisé] : ') or 'informatif'
    platform = await prompt('Plateforme [linkedin] : ') or 'linkedin'
    default = os.getenv('LINKEDIN_AUTHOR_URN', '') if platform == 'linkedin' else ''
    destination = await prompt(f'Compte ou destination [{default or "à configurer avant publication"}] : ') or default
    instructions = await prompt('Instructions éditoriales (facultatif) : ')
    return EditorialPreferences(tone=tone, platform=platform, destination=destination, instructions=instructions)


def show(state: WorkflowSnapshot) -> None:
    print(f'\nÉtat : {state.status.value} | recherches : {state.research_attempts} | appels LLM : {state.llm_calls}')
    if state.status == WorkflowStatus.WAITING_SYNTHESIS and state.synthesis:
        print(f'\nSynthèse v{state.synthesis.version}\n{state.synthesis.text}\n\nSources :')
        for i, doc in enumerate(state.synthesis.documents, 1):
            print(f'[{i}] {doc.url} — publication : {doc.published_at or "date inconnue"}')
        print('Contrôle : fidélité documentaire avec preuves textuelles ; validation humaine requise.')
    elif state.draft:
        print(f'\nBrouillon v{state.draft.version} — {state.draft.platform} — {state.draft.tone}')
        print(f'Destination : {state.draft.destination or "non configurée"}\n{state.draft.content}')
    if state.issues:
        print('\n' + '\n'.join(state.issues))
    if state.receipt:
        print(f'Publication : {state.receipt.status} {state.receipt.url or state.receipt.remote_id}')


async def review(handle) -> None:
    displayed = None
    while True:
        state = await handle.query(ContentWorkflow.snapshot)
        key = (state.status, state.research_attempts, state.editorial_attempts)
        if key != displayed:
            show(state)
            displayed = key
        if state.status in TERMINAL_STATES:
            return
        if state.status == WorkflowStatus.WAITING_SYNTHESIS:
            choice = await prompt('[v]alider / [d]onnées à corriger / [t]erminer / [q]uitter et reprendre plus tard : ')
            if choice == 'q':
                return
            if choice not in {'v', 'd', 't'}:
                continue
            decision = HumanDecision(
                stage='synthesis', version=state.synthesis.version,
                action={'v': 'approve', 'd': 'revise_data', 't': 'finish'}[choice],
                feedback=await revision_feedback() if choice == 'd' else '',
                preferences=await preferences() if choice == 'v' else None,
            )
        elif state.status == WorkflowStatus.WAITING_DRAFT:
            choice = await prompt('[v]alider / [s]tyle à corriger / [d]onnées à corriger / [t]erminer / [q]uitter : ')
            if choice == 'q':
                return
            if choice not in {'v', 's', 'd', 't'}:
                continue
            decision = HumanDecision(
                stage='draft', version=state.draft.version,
                action={'v': 'approve', 's': 'revise_style', 'd': 'revise_data', 't': 'finish'}[choice],
                feedback=await revision_feedback() if choice in {'s', 'd'} else '',
            )
        elif state.status == WorkflowStatus.WAITING_PUBLICATION:
            choice = await prompt('Publier cette version sur le compte affiché ? Saisir PUBLIER, terminer [t], ou quitter [q] : ')
            if choice == 'q':
                return
            if choice not in {'PUBLIER', 't'}:
                continue
            decision = HumanDecision(stage='publication', version=state.draft.version,
                                     action='publish' if choice == 'PUBLIER' else 'finish')
        else:
            await asyncio.sleep(1)
            continue
        try:
            await handle.execute_update(ContentWorkflow.decide, decision)
        except Exception:
            print('Décision refusée ou réponse interrompue ; relecture de l’état avant toute nouvelle action.')
        displayed = None
        await asyncio.sleep(0.2)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description='Recherche documentaire avec validations humaines persistantes')
    sub = root.add_subparsers(dest='command')
    for name in ('run', 'start'):
        cmd = sub.add_parser(name, help='Démarrer et suivre une tâche' if name == 'run' else 'Soumettre une tâche à un worker séparé')
        cmd.add_argument('question', nargs='?')
        cmd.add_argument('--date', help='Date de référence YYYY-MM-DD (défaut : date locale)')
        cmd.add_argument('--max-attempts', type=int, default=3)
    for name in ('resume', 'status'):
        sub.add_parser(name).add_argument('workflow_id')
    sub.add_parser('worker', help='Exécuter les deux workers sans interface interactive')
    cmd = sub.add_parser('decide', help='Envoyer une décision versionnée depuis un autre terminal')
    cmd.add_argument('workflow_id')
    cmd.add_argument('--stage', required=True, choices=['synthesis', 'draft', 'publication'])
    cmd.add_argument('--version', required=True, type=int)
    cmd.add_argument('--action', required=True, choices=['approve', 'revise_data', 'revise_style', 'publish', 'finish'])
    cmd.add_argument('--feedback', default='')
    cmd.add_argument('--tone', default='informatif')
    cmd.add_argument('--platform', default='linkedin')
    cmd.add_argument('--destination', default='')
    return root


async def run(args) -> None:
    client = await Client.connect(os.getenv('TEMPORAL_ADDRESS', 'localhost:7233'), data_converter=pydantic_data_converter)
    command = args.command or 'run'
    if command == 'worker':
        async with running_workers(client):
            print('Workers agent-search et agent-scraper démarrés. Ctrl+C pour arrêter.')
            await asyncio.Event().wait()
        return
    if command in {'status', 'decide', 'resume'}:
        handle = client.get_workflow_handle(args.workflow_id, result_type=WorkflowSnapshot)
        if command == 'status':
            print((await handle.query(ContentWorkflow.snapshot)).model_dump_json(indent=2))
            return
        if command == 'decide':
            prefs = None
            if args.stage == 'synthesis' and args.action == 'approve':
                prefs = EditorialPreferences(tone=args.tone, platform=args.platform, destination=args.destination)
            await handle.execute_update(ContentWorkflow.decide, HumanDecision(
                stage=args.stage, version=args.version, action=args.action,
                feedback=args.feedback, preferences=prefs,
            ))
            print('Décision enregistrée.')
            return
    else:
        question = getattr(args, 'question', None) or await prompt('Question : ')
        from datetime import date
        reference = date.fromisoformat(args.date) if getattr(args, 'date', None) else datetime.now(
            ZoneInfo(os.getenv('AGENTSEARCH_TIMEZONE', 'Europe/Paris'))
        ).date()
        request = make_request(question, reference, max_research_attempts=getattr(args, 'max_attempts', 3))
        handle = await client.start_workflow(
            ContentWorkflow.run, request, id=f'agent-search-{uuid.uuid4()}',
            task_queue=MAIN_TASK_QUEUE, execution_timeout=timedelta(days=30),
        )
        print(f'Identifiant de reprise : {handle.id}')
        if command == 'start':
            return
    async with running_workers(client):
        await review(handle)


def cli() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run(args))
    except (KeyboardInterrupt, EOFError):
        print('\nInterface arrêtée. La tâche peut être reprise avec son identifiant.')
    except Exception as exc:
        # Ne pas afficher de corps de réponse fournisseur susceptible de contenir des secrets.
        print(f'Échec ({type(exc).__name__}). Vérifier la configuration, Temporal et les journaux locaux.')
        raise SystemExit(1) from None
