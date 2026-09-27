# SpecToolBox - Reusable Pipeline Templates

Complete templates for creating data pipeline specifications and implementation guides for any project.

---

## 📋 Two Complementary Templates

### 1. REQUIREMENTS_TEMPLATE (Discovery & Approval Phase)

**File**: `DATA_PIPELINE_SPEC_TEMPLATE.md` (599 lines)

**Purpose**: Create a formal requirements document that needs stakeholder approval

**When to use**: 
- Starting a NEW pipeline project (before any code)
- Need to gather and document all requirements
- Want formal approval before implementation begins

**Output**: `specs/data_pipeline_{{PROJECT}}_spec.md`

**Key Sections**:
- Meta and Scope (project definition)
- Source File Contract (discover input structure)
- Schema & Types (define data model)
- Validation Error Strategy (define error handling)
- Persistence Contract (define output database)
- **Decision Log** (track all decisions made)
- **Acceptance Criteria** (sign-off checklist)
- Required Test Suite (quality requirements)
- Operational Runbook (production procedures)

**Workflow**:
```
1. Inspect project files, existing code, data sources
2. Copy template and fill in placeholders {{PLACEHOLDER}}
3. Document all discoveries and decisions
4. Get stakeholder approval (Section 14: Acceptance Criteria)
5. Archive as reference during implementation
```

**Example**: `specs/1_data-pipeline/data_pipeline_shopensemble_spec.md` (already exists in ShopEnsemble)

---

### 2. IMPLEMENTATION_TEMPLATE (Building & Execution Phase)

**File**: `FULL_DATA_PIPELINE_SPEC_TEMPLATE.md` (514 lines)

**Purpose**: Create a practical implementation guide with step-by-step instructions

**When to use**:
- Requirements are approved and you're ready to build
- Need practical guidance during implementation
- Want copy-paste commands and code examples
- Need quick reference for developers

**Output**: `specs/{{PROJECT}}-implementation-guide.md`

**Key Sections**:
- Project Context (why are we building this?)
- Data Model (exact structure with constraints)
- Validation Rules (all business rules documented)
- Pipeline Architecture (phases & flow)
- Database Design (schema with SQL DDL)
- **Implementation Checklist** (step-by-step tasks)
- **Commands & Usage** (copy-paste ready commands)
- Error Handling (recovery procedures)
- Performance Tuning (optimization guide)
- Quick Start (3 options to get started)

**Workflow**:
```
1. Read approved requirements spec
2. Copy this template
3. Customize based on approved requirements
4. Save as specs/{{PROJECT}}-implementation-guide.md
5. Use checklist to guide implementation
6. Reference commands during development
```

**Example**: `specs/1_data-pipeline/shopensemble-implementation-guide.md` (created for ShopEnsemble)

---

## 🔄 How Templates Relate

```
DATA_PIPELINE_SPEC_TEMPLATE.md
  ↓
  → Create: specs/data_pipeline_{{PROJECT}}_spec.md
  ↓
  → Stakeholders REVIEW & APPROVE
  ↓
  → Approved? Proceed to implementation
  ↓
FULL_DATA_PIPELINE_SPEC_TEMPLATE.md
  ↓
  → Create: specs/{{PROJECT}}-implementation-guide.md
  ↓
  → Developers FOLLOW the checklist
  ↓
  → Build pipeline
  ↓
  → Verify against requirements spec
```

---

## ✅ Template Comparison

| Aspect | Requirements Template | Implementation Template |
|--------|----------------------|------------------------|
| **Purpose** | "What do we need?" | "How do we build it?" |
| **When to use** | Before implementation | During implementation |
| **Audience** | Stakeholders, Architects | Developers, DevOps |
| **Placeholders** | Heavy ({{PLACEHOLDER}}) | Light (customizable) |
| **Code examples** | Minimal | Extensive (SQL, commands) |
| **Approval focus** | Yes (Section 14) | No (execution focus) |
| **Quick start** | No | Yes (Section 7) |
| **Decision tracking** | Yes (Appendix C) | No |
| **Checklists** | Yes (quality/test) | Yes (implementation) |

---

## 🚀 Quick Start by Role

### I'm a Project Lead (Starting a New Project)
1. Copy: `DATA_PIPELINE_SPEC_TEMPLATE.md`
2. Fill in: Replace all {{PLACEHOLDER}} with project data
3. Review with: Your team and stakeholders
4. Approve: Sign off in Section 14
5. Then hand to: Development team with implementation template

### I'm a Developer (Ready to Build)
1. Get: Approved `data_pipeline_{{PROJECT}}_spec.md` from lead
2. Copy: `FULL_DATA_PIPELINE_SPEC_TEMPLATE.md`
3. Customize: Based on approved requirements
4. Use: Implementation checklist (Section 6)
5. Run: Commands from Section 7
6. Reference: Validation rules from requirements spec

### I'm Creating a Second Pipeline (Learning from First)
1. Use: `DATA_PIPELINE_SPEC_TEMPLATE.md` for requirements
2. Use: `FULL_DATA_PIPELINE_SPEC_TEMPLATE.md` for implementation
3. Save time by: Copying patterns from ShopEnsemble specs
4. Adapt: Both templates to your project
5. Share: Results back to SpecToolBox if generally useful

---

## 📊 ShopEnsemble Project Example

This is how ShopEnsemble used both templates:

```
SpecToolBox/
├─ DATA_PIPELINE_SPEC_TEMPLATE.md          (Requirements template)
│  └─ Used to create:
│     specs/1_data-pipeline/data_pipeline_shopensemble_spec.md (Formal requirements)
│
└─ FULL_DATA_PIPELINE_SPEC_TEMPLATE.md     (Implementation template)
   └─ Used to create:
      specs/1_data-pipeline/shopensemble-implementation-guide.md (Dev guide with commands)
```

**Workflow**:
1. ✅ Requirements spec created & approved (formal document)
2. ✅ Implementation guide created (practical guide for developers)
3. → Developers follow implementation guide to build pipeline
4. → Test against requirements spec for validation

---

## 🤖 Agent Templates (Separate Pattern)

### 4. COORDINATOR_AGENT_SPEC_TEMPLATE (Conversational Coordinator/Orchestrator Agents)

**File**: `4_COORDINATOR_AGENT_SPEC_TEMPLATE.md`

**Purpose**: Reusable, full-maturity specification for an entry-point agent that classifies intent and routes queries to specialized sub-agents (semantic router / supervisor / ReAct patterns).

**Different from the pipeline templates above in one important way**: it's not split into a requirements-discovery template + a separate implementation template. It's **one holistic document** written at full target maturity from the start, with a built-in Roadmap/Phase-Mapping section (its own Section 14) whose status column gets updated in place as the project matures — mirroring how `1_data-pipeline/shopensemble-implementation-guide.md` itself was updated in place as its phases shipped, rather than forked into per-phase files. Don't create `-week3.md`, `-phase2.md`, etc. copies of a project spec built from this template; update the one file.

**Includes Section 8, UI Design & Frontend Integration** (added v2.0, 2026-09-17) — covers cold-start discoverability (does at least one view work for a user with zero prior knowledge of the data?), the home-page decision, verifying the chosen UI framework's actual import/execution mechanics against its installed source rather than assuming, a per-view checklist for data-browsing filters/volume/cross-view state, caching-scope pitfalls (framework caches are typically process-wide, not per-test), and shared response-rendering. Every item traces back to a real issue hit building ShopEnsemble's own UI (a `streamlit run` import bug invisible to the test suite, a late-discovered need for a catalog-browsing home page, a process-wide cache leaking state across tests) rather than generic UI-design boilerplate — the goal is catching these on the first pass instead of as follow-up patches.

**Also covers multi-turn conversation memory** (added v2.1, 2026-09-26) — Section 5 now asks where session memory lives, who issues the session ID, what is remembered (structured facts, never model-written prose), numeric bounds/TTL, lifetime, and how it interacts with a response cache (a context-resolved answer cached under bare query text leaks across sessions). Sections 3, 4, 8, 11, 13, 15, 16 gained matching items: per-sub-agent input cardinality ("both products" needs an N-entity tool or the router picks the wrong one), coordinator-side reference resolution with a deterministic identifier guard, lookup-key (ID) visibility on every rendered entity, STRIDE for session memory, multi-turn eval cases, and the async eval-harness event-loop pitfall. v2.2 adds four lessons found only by running the real system during implementation: never put a bearer session ID in a URL (server/proxy/client logs print it), partition the response cache between guarded and unguarded request paths, scope the identifier guard to a session's *empty first turn* (the model invents IDs from prompt examples), and measure prompt-rule changes with repeated A/B runs. v2.3 adds deterministic chitchat/greeting detection (no LLM call for the one obviously correct reply to "hi") and a shared, capability-describing line for every "couldn't help" message, rendered informationally rather than as a warning — from the ShopEnsemble Phase 7 spec. Every earlier item traces to the ShopEnsemble Phase 5 spec (`specs/2_coordinator-agent/shopensemble-coordinator-agent-phase5-session-memory-spec.md`). The template also now says how to add a capability *after* the first spec exists: fold analysis into the living spec, and only split a feature-named spec + mirrored plan when something concrete gets built.

**Output**: `specs/{{project}}-coordinator-agent-spec.md`

**Example**: `specs/2_coordinator-agent/shopensemble-coordinator-agent-spec.md` (ShopEnsemble's AI-agent coordinator, spanning Phase 1+)

---

## 🔍 When to Use Which

### Use Requirements Template if...
- [ ] Project is brand new (no code yet)
- [ ] Need to gather all requirements before starting
- [ ] Have stakeholders who need formal approval
- [ ] Want to track decisions made (Decision Log)
- [ ] Need acceptance criteria for QA sign-off
- [ ] Want operational runbook before going to production

### Use Implementation Template if...
- [ ] Requirements are already approved
- [ ] Ready to start building immediately
- [ ] Team needs practical step-by-step guidance
- [ ] Want copy-paste commands and code examples
- [ ] Need performance tuning guidance
- [ ] Want quick reference for developers

**Best Practice**: Use BOTH templates in sequence (Requirements → then Implementation)

---

## 💡 Key Differences Explained

### Requirements Template: "Discovery Mode"
- Heavy use of {{PLACEHOLDER}}
- Focus on "what" not "how"
- Captures decisions in Decision Log
- Formal approval gate (Section 14)
- Goes through review cycle
- Becomes reference document

**Example section**: 
```
## 9. Persistence Contract

### Destination database

| Table | System | Version | Schema provided | Indexes documented |
| :--- | :--- | :--- | :--- | :--- |
| `{{TABLE_1}}` | `{{DATABASE_SYSTEM}}` | `{{VERSION}}` | [Yes | No] | [Yes | No] |

[Heavy placeholders forcing inspection of actual requirements]
```

### Implementation Template: "Execution Mode"
- Concrete examples and commands
- Focus on "how" to build it
- Provides checklists to follow
- Quick starts and code samples
- Becomes reference during development
- Includes performance tuning

**Example section**:
```
## 7. Commands & Usage

### Run Dry Run
```bash
python -c "
from app.pipeline.orchestrator import run_dry_run
report = run_dry_run()
...
"
```

[Ready-to-run commands, no guessing]
```

---

## 🎯 Recommendation

**KEEP BOTH TEMPLATES** (not "one or the other"):
- ✅ Different workflows (discovery vs execution)
- ✅ Different audiences (stakeholders vs developers)
- ✅ No duplication (complementary, not redundant)
- ✅ Both under 600 lines (manageable size)
- ✅ Can be used in sequence for complete coverage

**Why not consolidate into one?**
- ✗ Would be 1000+ lines (too large)
- ✗ Mix approval gates with implementation details (confusing)
- ✗ Developers and stakeholders want different focuses
- ✗ Different workflows need different structures

---

## 🛠️ Customizing These Templates

When creating a new project pipeline:

### For Requirements (using DATA_PIPELINE_SPEC_TEMPLATE.md):
1. Replace `{{PROJECT_NAME}}` with actual project name
2. Replace `{{SOURCE_FILE_X}}` with actual source files
3. Inspect actual data and document findings
4. Fill in {{PLACEHOLDER}} sections with real data
5. Resolve all {{OPEN_DECISION}} items
6. Get sign-off in Section 14

### For Implementation (using FULL_DATA_PIPELINE_SPEC_TEMPLATE.md):
1. Replace `[Project Name]` headers with actual project
2. Update command examples with your functions
3. Modify database schema for your entities
4. Adjust validation rules from requirements
5. Update phase timeline for your project
6. Add specific commands for your setup

---

## 📚 Related Documentation

**In this SpecToolBox**:
- `DATA_PIPELINE_SPEC_TEMPLATE.md` - Requirements discovery template
- `FULL_DATA_PIPELINE_SPEC_TEMPLATE.md` - Implementation guide template
- `Data_Model_Spec_Template.md` - For data model specs (supplementary)

**In ShopEnsemble project** (Examples):
- `specs/1_data-pipeline/data_pipeline_shopensemble_spec.md` - Requirements (created from template)
- `specs/1_data-pipeline/shopensemble-implementation-guide.md` - Implementation (created from template)
- `Reference/Learning/datapipeline/` - Learning materials

---

## ✨ Version & Maintenance

- **Last Updated**: 2026-09-27
- **Template Version**: 1.0
- **Status**: Production ready for use
- **Maintenance**: Update if new best practices emerge

---

## 🎓 Examples

See ShopEnsemble project for real-world examples:
- Requirements: `specs/1_data-pipeline/data_pipeline_shopensemble_spec.md`
- Implementation: `specs/1_data-pipeline/shopensemble-implementation-guide.md`
- Learning: `Reference/Learning/datapipeline/`

Both templates were validated against ShopEnsemble's actual pipeline requirements.

---

**Start here**: Choose your role (project lead or developer) and follow the Quick Start section above!
