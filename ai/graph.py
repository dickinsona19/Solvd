"""The Smart Inbox agent, as a LangGraph state machine.

    START -> sort -> draft_<category> -> END

`sort` reads the message and assigns a category, a priority and a confidence.
The conditional edge then routes to the drafting node for that category, each
of which has its own prompt and its own idea of what a good reply looks like.
Drafting never runs without a sort, so an email costs two calls at most.

LLM calls go through OpenAI's Responses API (see model.py), not Chat
Completions — same path as the tradingnewsagent reference.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

try:  # Package import in the live server.
    from .model import DRAFT_MODEL, SORT_MODEL, get_llm
    from .prompts import (
        COMPANY_NAME,
        DRAFT_PROMPTS,
        GYM_INFO,
        POLICY,
        REPLY_RULES,
        SORT_PROMPT,
    )
except ImportError:  # Direct `python ai/run.py` compatibility.
    from model import DRAFT_MODEL, SORT_MODEL, get_llm
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


def _sort_node(llm, *, company_name: str, gym_info: str, policy: str):
    # json_schema is OpenAI's native structured output on the Responses API.
    model = llm.with_structured_output(EmailSort, method="json_schema", strict=True)
    # The sorter needs the policy too, not just the drafters. needs_human is
    # defined as "this would go beyond what we allow", which is unanswerable
    # without knowing what we allow.
    system = SORT_PROMPT.format(
        company_name=company_name,
        additional_company_details=gym_info,
        policy=policy,
    )

    def sort(state: InboxState) -> dict:
        result = model.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=render_email(state["email"])),
            ]
        )
        return {"sort": result.model_dump()}

    return sort


def _draft_node(
    llm,
    template: str,
    *,
    company_name: str,
    gym_info: str,
    policy: str,
):
    model = llm.with_structured_output(EmailDraft, method="json_schema", strict=True)
    system = template.format(
        company_name=company_name,
        additional_company_details=gym_info,
        policy=policy,
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
                SystemMessage(content=system),
                HumanMessage(content=context),
            ]
        )
        return {"draft": result.model_dump()}

    return draft


def _route(state: InboxState) -> str:
    return state.get("sort", {}).get("category", "other")


def build_graph(
    sort_model: str = SORT_MODEL,
    draft_model: str = DRAFT_MODEL,
    *,
    company_name: str = COMPANY_NAME,
    gym_info: str = GYM_INFO,
    policy: str = POLICY,
):
    """Wire and compile the graph for one tenant's policies and gym facts."""
    sorter = get_llm(sort_model)
    drafter = get_llm(draft_model)

    graph = StateGraph(InboxState)
    graph.add_node(
        "sort",
        _sort_node(
            sorter,
            company_name=company_name,
            gym_info=gym_info,
            policy=policy,
        ),
    )
    for category, template in DRAFT_PROMPTS.items():
        graph.add_node(
            f"draft_{category}",
            _draft_node(
                drafter,
                template,
                company_name=company_name,
                gym_info=gym_info,
                policy=policy,
            ),
        )

    graph.add_edge(START, "sort")
    graph.add_conditional_edges(
        "sort",
        _route,
        {category: f"draft_{category}" for category in DRAFT_PROMPTS},
    )
    for category in DRAFT_PROMPTS:
        graph.add_edge(f"draft_{category}", END)

    return graph.compile()
