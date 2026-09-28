"""Seed the agent registry from the playbook roster (18.4) and the corrected
delivery table. Placeholder owners — replace with the real user list from HR."""
import registry as R

R.init_registry()

# Placeholders. Real names/IDs come from HR; one person may own several agents.
P1, P3, P5 = "u_marketing", "u_hr", "u_research"
OPS, QUAL, EDU, CD = "u_ops", "u_quality", "u_principal", "u_clinical_director"
CW = "u_content_writer"

AGENTS = [
    # no,  name,                         board,        zone,   box,          profile,           cadence,     guardrail,                                                     owners
    ("01", "SEO Technical Auditor",      "p1-growth",  "green","n8n+agent",  "pod-p1-growth",   "weekly",    "Cannot deploy. Output is a ticket list for the web vendor.",   [(P1,"owner")]),
    ("02", "Keyword & Content Strategist","p1-growth", "green","agent",      "pod-p1-growth",   "weekly",    "Must use real volume data. Cannot invent search volumes.",     [(P1,"owner")]),
    ("03a","Clinical Evidence Table",    "p1-growth",  "amber","agent",      "pod-p1-growth",   "per piece", "Evidence table only. No prose, no draft. KURI ceiling at this stage.", [(P1,"owner"),(CD,"countersigner"),(CW,"consumer")]),
    ("03b","Clinical Content Drafter",   "p1-growth",  "amber","agent",      "p1-drafting",     "per piece", "Drafts ONLY from the signed claim set in the task. No web, no browser, no memory — enforced by toolset, not prompt. Every clinical statement carries a claim marker [C3]. Cannot fill a gap the claim set does not support. BELUM DIREVIEW watermark until the Clinical Director signs.", [(P1,"owner"),(CD,"countersigner")]),
    ("04", "GA4 & Funnel Analyst",       "p1-growth",  "green","n8n",        None,              "weekly",    "Aggregate exports only. No user-level data. Never condition-based audiences.", [(P1,"owner")]),
    ("05", "Local SEO & Reputation",     "p1-growth",  "amber","n8n+agent",  "pod-p1-growth",   "weekly",    "Any review alleging a clinical issue routes to Clinical Director and EXITS the agent workflow.", [(P1,"owner"),(CD,"countersigner")]),
    ("06", "Paid Media Operator",        "p1-growth",  "amber","seat",       None,              "weekly",    "Clinical-and-legal gate before live. No superiority/cure claims, no crisis-page retargeting.", [(P1,"owner"),(CD,"countersigner")]),

    ("07a","Risk-Language Gate",         "p2-access",  "amber","n8n",        None,              "continuous","DETERMINISTIC. Fail-closed, recall-tuned, irreversible per conversation, runs BEFORE any model sees text. Never agentic.", [(OPS,"owner"),(CD,"countersigner")]),
    ("07b","Enquiry Router",             "p2-access",  "green","n8n",        None,              "continuous","Administrative classification only. Never assesses clinical urgency.", [(OPS,"owner")]),
    ("07c","Triage Script Curator",      "p2-access",  "amber","n8n+agent",  "pod-p2-access",   "weekly",    "Reads LOGS ONLY, never live conversations. Scripts approved by Clinical Director.", [(OPS,"owner"),(CD,"countersigner")]),
    ("08", "Booking & No-Show Analyst",  "p2-access",  "green","n8n",        None,              "monthly",   "Aggregate, de-identified before reaching any AI tool. Operations decide.", [(OPS,"owner")]),
    ("09", "Referral Network Coordinator","p2-access", "amber","agent",      "pod-p2-access",   "monthly",   "Produces the TEMPLATE, never the instance. Outcome comms written by a clinician with documented consent.", [(OPS,"owner"),(CD,"countersigner")]),

    ("10", "Job Analysis & JD Writer",   "p3-people",  "green","agent",      "pod-p3-people",   "batch",     "Validated by the role's actual supervisor. AI consistency is not accuracy.", [(P3,"owner")]),
    ("11a","Recruitment Kit Builder",    "p3-people",  "green","agent",      "pod-p3-people",   "per vacancy","Produces ads/rubrics BEFORE any candidate exists. Never sees a CV.", [(P3,"owner")]),
    ("11b","CV Extractor",               "p3-people",  "amber","n8n",        None,              "per vacancy","Declared facts into fixed columns. No free-text column. Never infers to fill a blank.", [(P3,"owner")]),
    ("11c","Criteria Flagger",           "p3-people",  "amber","n8n",        None,              "per vacancy","Flags met/not met/not stated against PUBLISHED criteria. Never ranks. Never removes a row. Fixed sort order.", [(P3,"owner")]),
    ("12", "Onboarding & Documentation", "p3-people",  "green","n8n+agent",  "pod-p3-people",   "ongoing",   "Legal/compliance content verified against current Indonesian regulation by a human before issue.", [(P3,"owner")]),
    ("13", "Workforce & L&D Architect",  "p3-people",  "green","seat",       None,              "quarterly", "Clinical competency standards set by clinical leadership; the agent structures, it does not define competence.", [(P3,"owner")]),

    ("14", "SOP & Pathway Documentation","p4-quality", "amber","agent",      "pod-p4-quality",  "ongoing",   "Clinical content ORIGINATES FROM CLINICIANS. Edits and structures; does not author protocol.", [(QUAL,"owner"),(CD,"countersigner")]),
    ("15", "Competency & OSCE Materials","p4-quality", "amber","seat",       None,              "per cycle", "Scenarios clinically validated before use. Assessment decisions made by human assessors.", [(QUAL,"owner"),(CD,"countersigner")]),
    ("16", "Quality Indicator Reporting","p4-quality", "amber","n8n+agent",  "pod-p4-quality",  "monthly",   "Aggregate, de-identified. Interpretation of a clinical trend is a clinical judgement.", [(QUAL,"owner"),(CD,"countersigner")]),

    ("17", "Literature & Evidence",      "p5-research","green","agent",      "pod-p5-research", "monthly",   "EVERY citation verified to exist and to say what the summary claims. Verification is not optional.", [(P5,"owner")]),
    ("18", "Protocol & Analysis Assistant","p5-research","amber","seat",     None,              "per project","De-identified data only, only where ethics approval permits. Statistical conclusions verified by a qualified analyst.", [(P5,"owner"),(CD,"countersigner")]),

    ("19", "Curriculum & Materials",     "p6-education","amber","seat",      None,              "ongoing",   "An individual child's IEP content is written by their teacher and therapist. No named student data.", [(EDU,"owner")]),
    ("20", "Admissions & Parent Comms",  "p6-education","green","seat",      None,              "weekly",    "No individual student or family information.", [(EDU,"owner")]),
]

for a in AGENTS:
    R.register(agent_no=a[0], name=a[1], board=a[2], zone=a[3],
               delivery_box=a[4], profile=a[5], cadence=a[6],
               guardrail=a[7], owners=a[8])

print(f"registered {len(AGENTS)} agent roles")
