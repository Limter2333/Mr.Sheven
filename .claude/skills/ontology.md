---
name: ontology
description: Typed knowledge graph for structured memory and entity relationships. Use when creating/querying entities (Person, Project, Task, Event, Document), linking objects, or tracking dependencies.
user_invocable: true
---

# Ontology — Knowledge Graph

A typed vocabulary + constraint system for representing knowledge as a verifiable graph.

## Core Concept

Everything is an **entity** with a **type**, **properties**, and **relations** to other entities.

```
Entity: { id, type, properties, relations, created, updated }
Relation: { from_id, relation_type, to_id, properties }
```

## When to Use

| Trigger | Action |
|---------|--------|
| "Remember that..." | Create/update entity |
| "What do I know about X?" | Query graph |
| "Link X to Y" | Create relation |
| "Show all tasks for project Z" | Graph traversal |
| "What depends on X?" | Dependency query |
| Planning multi-step work | Model as graph transformations |

## Core Types

```yaml
Person: { name, email?, phone?, notes? }
Organization: { name, type?, members[] }
Project: { name, status, goals[], owner? }
Task: { title, status, due?, priority?, assignee?, blockers[] }
Goal: { description, target_date?, metrics[] }
Event: { title, start, end?, location?, attendees[], recurrence? }
Location: { name, address?, coordinates? }
Document: { title, path?, url?, summary? }
Message: { content, sender, recipients[], thread? }
Note: { content, tags[], refs[] }
Account: { service, username, credential_ref? }
Device: { name, type, identifiers[] }
Credential: { service, secret_ref }  # Never store secrets directly
Action: { type, target, timestamp, outcome? }
Policy: { scope, rule, enforcement }
```

## Storage

Default: `memory/ontology/graph.jsonl` (append-only JSONL)

```jsonl
{"op":"create","entity":{"id":"p_001","type":"Person","properties":{"name":"Alice"}}}
{"op":"create","entity":{"id":"proj_001","type":"Project","properties":{"name":"Website Redesign","status":"active"}}}
{"op":"relate","from":"proj_001","rel":"has_owner","to":"p_001"}
```

### Append-Only Rule

When working with existing ontology data, **append/merge** changes instead of overwriting. This preserves history.

## Workflows

### Create Entity
```bash
python3 .claude/skills/scripts/ontology.py create --type Person --props '{"name":"Alice","email":"alice@example.com"}'
```

### Query
```bash
python3 .claude/skills/scripts/ontology.py query --type Task --where '{"status":"open"}'
python3 .claude/skills/scripts/ontology.py get --id task_001
python3 .claude/skills/scripts/ontology.py related --id proj_001 --rel has_task
```

### Link Entities
```bash
python3 .claude/skills/scripts/ontology.py relate --from proj_001 --rel has_task --to task_001
```

### Validate
```bash
python3 .claude/skills/scripts/ontology.py validate
```

## Constraints

Define in `memory/ontology/schema.yaml`:

```yaml
types:
  Task:
    required: [title, status]
    status_enum: [open, in_progress, blocked, done]
  Event:
    required: [title, start]
    validate: "end >= start if end exists"
  Credential:
    required: [service, secret_ref]
    forbidden_properties: [password, secret, token]

relations:
  has_owner:
    from_types: [Project, Task]
    to_types: [Person]
    cardinality: many_to_one
  blocks:
    from_types: [Task]
    to_types: [Task]
    acyclic: true
```

## Planning as Graph Transformation

Model multi-step plans as graph operations:

```
Plan: "Schedule team meeting and create follow-up tasks"
1. CREATE Event { title: "Team Sync", attendees: [p_001, p_002] }
2. RELATE Event -> has_project -> proj_001
3. CREATE Task { title: "Prepare agenda", assignee: p_001 }
4. RELATE Task -> for_event -> event_001
```

## Quick Start

```bash
mkdir -p memory/ontology
touch memory/ontology/graph.jsonl

python3 .claude/skills/scripts/ontology.py schema-append --data '{
  "types": {
    "Task": { "required": ["title", "status"] },
    "Project": { "required": ["name"] },
    "Person": { "required": ["name"] }
  }
}'

python3 .claude/skills/scripts/ontology.py create --type Person --props '{"name":"Alice"}'
python3 .claude/skills/scripts/ontology.py list --type Person
```

## References

- `.claude/skills/references/ontology-schema.md` — Full type definitions and constraint patterns
- `.claude/skills/references/ontology-queries.md` — Query language and traversal examples
