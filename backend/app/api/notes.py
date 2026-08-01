import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.paper import Paper
from app.models.project import Project
from app.models.note import Note
from app.api.auth import get_current_user
from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse

router = APIRouter(prefix="/notes", tags=["notes"])

SUMMARIZE_PROMPT = """你是阅读笔记提炼助手。根据摘录片段提炼 2-3 条要点（每条一句话，用 "- " 开头）。
只输出要点列表，不要输出其他文字。

摘录片段：
{text}"""


def _to_response(note: Note) -> NoteResponse:
    tags = []
    if note.tags:
        try:
            parsed = json.loads(note.tags)
            if isinstance(parsed, list):
                tags = [str(t) for t in parsed]
        except Exception:
            pass
    return NoteResponse(
        id=note.id,
        paper_id=note.paper_id,
        project_id=note.project_id,
        anchor_text=note.anchor_text,
        content=note.content,
        tags=tags,
        ai_summary=note.ai_summary,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _summarize(text: str) -> str:
    from app.services.llm import LLMService

    return (
        LLMService.chat(
            messages=[{"role": "system", "content": SUMMARIZE_PROMPT.format(text=text[:3000])}],
            temperature=0.3,
            max_tokens=512,
            feature="notes",
        )
        or ""
    ).strip()


@router.post("", response_model=NoteResponse, status_code=201)
def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(Paper.id == data.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    project = (
        db.query(Project)
        .filter(Project.id == paper.project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    note = Note(
        user_id=current_user.id,
        paper_id=paper.id,
        project_id=paper.project_id,
        anchor_text=data.anchor_text,
        content=data.content,
        tags=json.dumps(data.tags, ensure_ascii=False) if data.tags else None,
    )
    if data.summarize and (note.anchor_text or note.content):
        try:
            note.ai_summary = _summarize(note.anchor_text or note.content or "")
        except Exception:
            note.ai_summary = None
    db.add(note)
    db.commit()
    db.refresh(note)
    return _to_response(note)


@router.post("/{note_id}/summarize", response_model=NoteResponse)
def summarize_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = _get_owned_note(db, current_user, note_id)
    source = note.anchor_text or note.content
    if not source:
        raise HTTPException(status_code=400, detail="该笔记没有可提炼的内容")
    note.ai_summary = _summarize(source)
    db.commit()
    db.refresh(note)
    return _to_response(note)


@router.get("", response_model=list[NoteResponse])
def list_notes(
    paper_id: Optional[int] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Note).filter(Note.user_id == current_user.id)
    if paper_id is not None:
        query = query.filter(Note.paper_id == paper_id)
    if project_id is not None:
        query = query.filter(Note.project_id == project_id)
    notes = query.order_by(Note.created_at.desc()).all()
    return [_to_response(n) for n in notes]


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    data: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = _get_owned_note(db, current_user, note_id)
    if data.anchor_text is not None:
        note.anchor_text = data.anchor_text
    if data.content is not None:
        note.content = data.content
    if data.tags is not None:
        note.tags = json.dumps(data.tags, ensure_ascii=False)
    db.commit()
    db.refresh(note)
    return _to_response(note)


@router.delete("/{note_id}", status_code=200)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = _get_owned_note(db, current_user, note_id)
    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}


@router.get("/export", response_class=Response)
def export_notes(
    project_id: int = Query(...),
    paper_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export notes as Markdown, grouped by paper."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = db.query(Note).filter(
        Note.user_id == current_user.id, Note.project_id == project_id
    )
    if paper_id is not None:
        query = query.filter(Note.paper_id == paper_id)
    notes = query.order_by(Note.paper_id.asc(), Note.created_at.asc()).all()

    # Group by paper, preserving paper order
    title_by_id = {
        p.id: p.title for p in db.query(Paper).filter(
            Paper.project_id == project_id, Paper.id.in_({n.paper_id for n in notes})
        ).all()
    } if notes else {}

    lines = [f"# 阅读笔记 — {project.name}", ""]
    current_paper = None
    for n in notes:
        if n.paper_id != current_paper:
            current_paper = n.paper_id
            title = title_by_id.get(n.paper_id, f"论文 {n.paper_id}")
            lines.append(f"## 《{title}》")
            lines.append("")
        if n.anchor_text:
            lines.append(f"- **摘录**：“{n.anchor_text}”")
        if n.content:
            lines.append(f"- **笔记**：{n.content}")
        if n.tags:
            try:
                tags = json.loads(n.tags)
                if isinstance(tags, list) and tags:
                    lines.append(f"- **标签**：{'、'.join(str(t) for t in tags)}")
            except Exception:
                pass
        if n.ai_summary:
            lines.append(f"- **AI 提炼**：\n\n{n.ai_summary}")
        lines.append("")

    body = "\n".join(lines).strip() or "（暂无笔记）"
    filename = f"notes_{project.name}.md"
    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _get_owned_note(db: Session, current_user: User, note_id: int) -> Note:
    note = (
        db.query(Note)
        .filter(Note.id == note_id, Note.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note
