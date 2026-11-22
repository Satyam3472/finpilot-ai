"""A text-only boundary around the existing Google ADK runner."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from backend.schemas import ChatHistory, ChatSession, ChatWrite

router = APIRouter(prefix="/chat", tags=["chat"])
APP_NAME = "finance_agent"


def identity(request: Request) -> dict[str, str]:
    return {"app_name": APP_NAME, "user_id": request.app.state.local_user}


def session_info(session) -> dict:
    return {
        "id": session.id,
        "title": session.state.get("title", "New conversation"),
        "updated_at": session.last_update_time,
    }


def message_text(event) -> str:
    if not event.content or event.get_function_calls() or event.get_function_responses():
        return ""
    return "".join(part.text or "" for part in event.content.parts or [] if not part.thought)


def history_messages(session, root_name: str) -> list[dict]:
    # Keep the final coordinator text per user turn. Specialist branches and tool
    # events can exist in the persisted trace and are never returned to the browser.
    messages = []
    reply = ""
    for event in session.events:
        if event.partial:
            continue
        text = message_text(event)
        if event.author == "user" and event.content and event.content.role == "user" and text:
            if reply:
                messages.append({"role": "assistant", "text": reply})
                reply = ""
            messages.append({"role": "user", "text": text})
        elif event.author == root_name and not event.branch and event.is_final_response() and text:
            reply = text
    if reply:
        messages.append({"role": "assistant", "text": reply})
    return messages


async def find_session(request: Request, session_id: UUID):
    session = await request.app.state.sessions.get_session(
        **identity(request), session_id=str(session_id)
    )
    if session is None:
        raise HTTPException(404, "Conversation not found.")
    return session


@router.get("/sessions", response_model=list[ChatSession])
async def list_sessions(request: Request) -> list[dict]:
    result = await request.app.state.sessions.list_sessions(**identity(request))
    return sorted(
        (session_info(item) for item in result.sessions),
        key=lambda item: item["updated_at"], reverse=True,
    )


@router.post("/sessions", response_model=ChatSession, status_code=201)
async def new_session(request: Request) -> dict:
    return session_info(await request.app.state.sessions.create_session(**identity(request)))


@router.get("/sessions/{session_id}", response_model=ChatHistory)
async def get_history(request: Request, session_id: UUID) -> dict:
    session = await find_session(request, session_id)
    return {
        **session_info(session),
        "messages": history_messages(session, request.app.state.runner.agent.name),
    }


def sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/messages", response_class=StreamingResponse)
async def send_message(request: Request, session_id: UUID, body: ChatWrite) -> StreamingResponse:
    session = await find_session(request, session_id)
    state = request.app.state
    if session.id in state.active_sessions:
        raise HTTPException(409, "A reply is already in progress for this conversation.")
    state.active_sessions.add(session.id)

    async def stream():
        final_text = ""
        try:
            title = {"title": " ".join(body.message.split())[:72]} if "title" not in session.state else None
            async with asyncio.timeout(90):
                async for event in state.runner.run_async(
                    user_id=state.local_user,
                    session_id=session.id,
                    new_message=types.Content(
                        role="user", parts=[types.Part.from_text(text=body.message)]
                    ),
                    state_delta=title,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=18),
                ):
                    if event.author != state.runner.agent.name or event.branch:
                        continue
                    text = message_text(event)
                    if event.partial and text:
                        yield sse("delta", {"text": text})
                    elif event.is_final_response() and text:
                        final_text = text
            if final_text:
                yield sse("done", {"text": final_text})
            else:
                request.state.sanitized_error = "empty_assistant_reply"
                yield sse("error", {"message": "The assistant returned no reply. Try again."})
        except Exception:
            # Provider exceptions can contain user or configuration details.
            request.state.sanitized_error = "assistant_unavailable"
            yield sse("error", {"message": "The assistant is unavailable. Check the Gemini configuration or try again."})
        finally:
            state.active_sessions.discard(session.id)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )
