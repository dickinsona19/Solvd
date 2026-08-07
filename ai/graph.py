"""The Smart Inbox agent, as a LangGraph state machine.

    START -> sort -> draft_<category> -> END

`sort` reads the message and assigns a category, a priority and a confidence.
The conditional edge then routes to the drafting node for that category, each
of which has its own prompt and its own idea of what a good reply looks like.
Drafting never runs without a sort, so an email costs two calls at most.
"""

from __future__ import annotations

import os
from typing import Literal, NotRequired, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from prompts import (
    COMPANY_NAME,
    DRAFT_PROMPTS,
    GYM_INFO,
    POLICY,
    REPLY_RULES,
    SORT_PROMPT,
)

Category = Literal["billing", "membership", "schedule", "lead", "facilities", "other"]
Priority = Literal["high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]

# Both passes run on the same model. The 5.6 line has no small tier, so the
# old split of a cheap sorter and an expensive drafter is gone: set
# SOLVD_SORT_MODEL to a nano model if the call volume ever makes that matter.
SORT_MODEL = os.getenv("SOLVD_SORT_MODEL", "gpt-5.6-luna")
DRAFT_MODEL = os.getenv("SOLVD_DRAFT_MODEL", "gpt-5.6-luna")


class EmailSort(BaseModel):
    """How the inbox should file and rank one message."""

    category: Category = Field(description="Which queue this message belongs in")
    priority: Priority = Field(description="How soon the owner needs to deal with it")
    needs_human: bool = Field(
        description="True when the owner should read and rewrite the reply themselves"
    )
    confidence: Confidence = Field(description="Confidence in the category and priority")
    summary: str = Field(description="One short sentence, in the owner's words")
    reasoning: str = Field(description="Why this category and priority")


class EmailDraft(BaseModel):
    """A reply the owner can send, approve, or throw away."""

    reply: str = Field(description="The reply body, ready to send as is")
    action: str = Field(description="The one system change this reply commits to")
    confidence: Confidence = Field(
        description="Confidence that this reply can be sent without edits"
    )


class InboxState(TypedDict):
    """What flows through the graph. One email in, sort and draft out."""

    email: dict
    sort: NotRequired[dict]
    draft: NotRequired[dict]


def render_email(email: dict) -> str:
    """Flatten a message plus its member record into the user turn.

    The member context is the whole point of the feature: "I want to cancel"
    from an eighteen-week regular and from a two-week trial are not the same
    email, and the draft should not read as though they were.
    """
    lines = [f"From: {email['name']}"]

    if email.get("meta"):
        lines.append(f"Member record: {email['meta']}")
    if email.get("risk"):
        lines.append(f"Churn radar: {email['risk']['label']} out of 100")
    if email.get("receivedAt"):
        lines.append(f"Received: {email['receivedAt']}")

    lines += [f"Subject: {email['subject']}", "", email["message"]]
    return "\n".join(lines)


def _sort_node(llm):
    model = llm.with_structured_output(EmailSort)
    # The sorter needs the policy too, not just the drafters. needs_human is
    # defined as "this would go beyond what we allow", which is unanswerable
    # without knowing what we allow.
    system = SORT_PROMPT.format(
        company_name=COMPANY_NAME,
        additional_company_details=GYM_INFO,
        policy=POLICY,
    )

    def sort(state: InboxState) -> dict:
        result = model.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": render_email(state["email"])},
            ]
        )
        return {"sort": result.model_dump()}

    return sort


def _draft_node(llm, template: str):
    model = llm.with_structured_output(EmailDraft)
    system = template.format(
        company_name=COMPANY_NAME,
        additional_company_details=GYM_INFO,
        policy=POLICY,
        reply_rules=REPLY_RULES,
    )

    def draft(state: InboxState) -> dict:
        # The sort pass already read the message. Handing its summary to the
        # drafter keeps the two halves from disagreeing about what was asked.
        context = render_email(state["email"])
        if summary := state.get("sort", {}).get("summary"):
            context += f"\n\n(Sorted as: {summary})"

        result = model.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ]
        )
        return {"draft": result.model_dump()}

    return draft


def _route(state: InboxState) -> str:
    return state.get("sort", {}).get("category", "other")


def build_graph(sort_model: str = SORT_MODEL, draft_model: str = DRAFT_MODEL):
    """Wire and compile the graph. One instance handles every email."""
    sorter = ChatOpenAI(model=sort_model)
    drafter = ChatOpenAI(model=draft_model)

    graph = StateGraph(InboxState)
    graph.add_node("sort", _sort_node(sorter))
    for category, template in DRAFT_PROMPTS.items():
        graph.add_node(f"draft_{category}", _draft_node(drafter, template))

    graph.add_edge(START, "sort")
    graph.add_conditional_edges(
        "sort",
        _route,
        {category: f"draft_{category}" for category in DRAFT_PROMPTS},
    )
    for category in DRAFT_PROMPTS:
        graph.add_edge(f"draft_{category}", END)

    return graph.compile()
