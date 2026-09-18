Conception d'un agent 

Je voudrais un Agent Orchestrateur qui vas surveiller les 4 autres.
L'orchestrateur vas anaylser la demande, planifier le travail, distribue les taches et verifier les resultats.

Il existe un agent pour la recherche sur le web et les sources, un agent pour verifier les faits et les comparer, ensuite un agent pour rediger un articje

## Architecture
```

                         USER
                           │
                           ↓
                 ┌───────────────────┐
                 │   ORCHESTRATOR    │
                 │                   │
                 │ Planner           │
                 │ Task Manager      │
                 │ State Manager     │
                 │ Decision Maker    │
                 └─────────┬─────────┘
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ↓                ↓                 ↓
     ┌─────────┐      ┌───────────┐    ┌──────────┐
     │Research │      │Fact Check │    │ Writer   │
     └────┬────┘      └─────┬─────┘    └────┬─────┘
          │                 │               │
          ↓                 ↓               ↓
       Sources           Claims          Article
          │                 │               │
          └─────────────────┼───────────────┘
                            ↓
                   ┌─────────────────┐
                   │ Quality Control │
                   └────────┬────────┘
                            │
                     ┌──────┴──────┐
                     ↓             ↓
                   FAIL           PASS
                     │             │
                     └──→ Loop     ↓
                                OUTPUT
```